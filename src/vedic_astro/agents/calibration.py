"""
calibration.py — Chart-aware weight calibration.

Generates personalised questions from the natal chart and runs a convergence
loop that adjusts factor weights until the model's predictions match the user's
answers. Calibrated weights feed into Phase 3 scoring.

    questions = generate_questions(pipeline_state)
    result    = calibrate_convergence(questions, user_answers, pipeline_state)
    # result.weights → pass to predict()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Question bank
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CalibrationQuestion:
    """A single calibration question."""
    id: str
    text: str
    domain_factor: str          # which weight this validates: dasha|natal|transit|yoga|bhava
    predicted_timing: str       # what the chart predicts (shown to user after answering)
    answer_type: str            # "year" | "yes_no" | "description" | "period"
    options: list[str] = field(default_factory=list)   # MCQ choices shown to user
    skippable: bool = True


# Full bank — questions are selected based on chart features
_QUESTION_BANK: list[dict] = [
    # Career
    {
        "id": "career_start",
        "text": "In what year did you start your current career, business, or have a major professional breakthrough?",
        "domain_factor": "dasha",
        "answer_type": "year",
        "category": "career",
        "trigger": "career",          # show if domain_key in chart features
    },
    {
        "id": "career_change",
        "text": "Have you had a significant career change, job loss, or promotion? If yes, in what year?",
        "domain_factor": "transit",
        "answer_type": "year",
        "category": "career",
        "trigger": "any",
    },
    # Marriage/Relationship
    {
        "id": "marriage_year",
        "text": "Are you married or in a committed long-term relationship? If yes, approximately what year did it begin?",
        "domain_factor": "dasha",
        "answer_type": "year",
        "category": "marriage",
        "trigger": "any",
    },
    {
        "id": "relationship_challenge",
        "text": "Have you experienced a significant relationship breakup, divorce, or separation? If yes, what year?",
        "domain_factor": "transit",
        "answer_type": "year",
        "category": "marriage",
        "trigger": "7th_afflicted",
    },
    # Children
    {
        "id": "first_child",
        "text": "Do you have children? If yes, in what year was your first child born?",
        "domain_factor": "dasha",
        "answer_type": "year",
        "category": "children",
        "trigger": "any",
    },
    # Wealth
    {
        "id": "wealth_gain",
        "text": "Have you had a major financial windfall (inheritance, business success, investment gain)? If yes, approximately what year?",
        "domain_factor": "yoga",
        "answer_type": "year",
        "category": "wealth",
        "trigger": "dhana_yoga",
    },
    {
        "id": "wealth_loss",
        "text": "Have you experienced a significant financial setback or loss? If yes, approximately what year?",
        "domain_factor": "transit",
        "answer_type": "year",
        "category": "wealth",
        "trigger": "any",
    },
    # Health
    {
        "id": "health_event",
        "text": "Have you had a significant health issue, illness, surgery, or accident? If yes, what year?",
        "domain_factor": "dasha",
        "answer_type": "year",
        "category": "health",
        "trigger": "any",
    },
    # Travel / Relocation
    {
        "id": "foreign_move",
        "text": "Have you lived, worked, or studied abroad? If yes, approximately when did you first relocate?",
        "domain_factor": "dasha",
        "answer_type": "year",
        "category": "travel",
        "trigger": "any",
    },
    # Education
    {
        "id": "education",
        "text": "In what year did you complete your highest level of formal education (degree/diploma)?",
        "domain_factor": "natal",
        "answer_type": "year",
        "category": "education",
        "trigger": "any",
    },
    # Family loss
    {
        "id": "family_loss",
        "text": "Have you experienced a significant personal loss (close family member or friend)? If yes, what year?",
        "domain_factor": "transit",
        "answer_type": "year",
        "category": "family",
        "trigger": "any",
    },
    # Spirituality
    {
        "id": "spiritual",
        "text": "Have you had a significant spiritual, religious, or philosophical turning point? If yes, what year?",
        "domain_factor": "natal",
        "answer_type": "year",
        "category": "spirituality",
        "trigger": "9th_strong",
    },
    # Current dasha feel
    {
        "id": "current_period",
        "text": "How would you describe the last 2 years of your life overall?",
        "domain_factor": "dasha",
        "answer_type": "period",
        "category": "general",
        "trigger": "any",
    },
    # Overall life satisfaction
    {
        "id": "life_phase",
        "text": "Which phase of life are you currently in? (Building / Peak / Transition / Consolidation)",
        "domain_factor": "natal",
        "answer_type": "description",
        "category": "general",
        "trigger": "any",
    },
    # Yoga validation
    {
        "id": "raj_yoga",
        "text": "Have you achieved a position of authority, leadership, or significant public recognition?",
        "domain_factor": "yoga",
        "answer_type": "yes_no",
        "category": "career",
        "trigger": "raj_yoga",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Question selection
# ─────────────────────────────────────────────────────────────────────────────

def generate_questions(state: Any, n: int = 10) -> list[CalibrationQuestion]:
    """
    Select the n most chart-relevant calibration questions.

    Parameters
    ----------
    state : PipelineState (after compute_chart completes)
    n     : number of questions (default 10)

    Returns
    -------
    list[CalibrationQuestion]
    """
    # Extract chart features to decide which questions apply
    features = _extract_chart_features(state)
    selected: list[dict] = []

    # Always include the "any" triggered questions first, then specialised ones
    any_questions   = [q for q in _QUESTION_BANK if q["trigger"] == "any"]
    special_questions = [q for q in _QUESTION_BANK if q["trigger"] != "any"]

    # Filter specialised questions based on features
    relevant_special = [
        q for q in special_questions
        if _question_is_relevant(q, features)
    ]

    # Build pool: always-include + relevant specials
    pool = any_questions + relevant_special

    # Deduplicate by id, keep insertion order
    seen: set[str] = set()
    for q in pool:
        if q["id"] not in seen:
            seen.add(q["id"])
            selected.append(q)
        if len(selected) >= n:
            break

    # Pad with remaining if needed
    if len(selected) < n:
        for q in _QUESTION_BANK:
            if q["id"] not in seen:
                seen.add(q["id"])
                selected.append(q)
            if len(selected) >= n:
                break

    return [
        CalibrationQuestion(
            id=q["id"],
            text=q["text"],
            domain_factor=q["domain_factor"],
            predicted_timing=_get_predicted_timing(q["id"], state),
            answer_type=q["answer_type"],
            options=_generate_options(q["answer_type"], state),
        )
        for q in selected[:n]
    ]


def _extract_chart_features(state: Any) -> dict:
    """Extract simple boolean features for question selection."""
    features: dict[str, bool] = {
        "career": True,
        "marriage": True,
        "health": True,
        "any": True,
    }
    try:
        if state.yoga_bundle:
            yoga_names = [y.name.lower() for y in state.yoga_bundle.active_yogas]
            features["dhana_yoga"]  = any("dhana" in n for n in yoga_names)
            features["raj_yoga"]    = any("raj" in n or "raja" in n for n in yoga_names)
        if state.chart:
            from vedic_astro.engines.natal_engine import PlanetName
            planets = state.chart.planets
            # 7th afflicted if Mars/Saturn/Rahu in 7th
            house7_planets = [p.value for p, pos in planets.items() if pos.house == 7]
            features["7th_afflicted"] = any(
                p in ("mars", "saturn", "rahu") for p in house7_planets
            )
            # 9th strong if Jupiter/Sun in 9th or 9th lord well-placed
            house9_planets = [p.value for p, pos in planets.items() if pos.house == 9]
            features["9th_strong"] = bool(house9_planets)
    except Exception as exc:
        logger.debug("Chart feature extraction partial failure: %s", exc)
    return features


def _question_is_relevant(question: dict, features: dict) -> bool:
    trigger = question.get("trigger", "any")
    if trigger == "any":
        return True
    return bool(features.get(trigger, False))


_PERIOD_OPTIONS = [
    "Thriving — exceptional growth and gains",
    "Positive — steady progress with minor setbacks",
    "Mixed — equal highs and lows",
    "Challenging — significant difficulties",
    "Very difficult — major losses or crises",
    "Not applicable / Skip",
]

_LIFE_PHASE_OPTIONS = [
    "Building — establishing career, relationships, foundation",
    "Peak — at my most successful and active",
    "Transition — going through major changes",
    "Consolidation — slowing down, reflecting, wisdom phase",
    "Not applicable / Skip",
]

_YES_NO_OPTIONS = ["Yes", "No", "Not applicable / Skip"]


def _generate_dasha_year_options(state: Any) -> list[str]:
    """
    Build MCQ options for year questions from the dasha timeline.
    Each option is labelled with the dasha lord and its year range,
    e.g. "Saturn period (2008–2026)".  Adult life only (age 15 onward).
    Always ends with a Skip option.
    """
    skip = "Not applicable / Skip"
    try:
        from datetime import date as _date
        from vedic_astro.engines.dasha_engine import compute_maha_dashas
        from vedic_astro.engines.natal_engine import PlanetName

        moon_lon = state.chart.planets[PlanetName.MOON].longitude
        b = state.request.birth
        birth_dt = _date(b.year, b.month, b.day)
        adult_year = b.year + 15
        current_year = _date.today().year + 5   # allow near-future options

        all_mahas = compute_maha_dashas(moon_lon, birth_dt)
        options: list[str] = []
        for m in all_mahas:
            m_start = m.start.year
            m_end   = m.end.year
            # Include periods that overlap with adult life up to 5 years ahead
            if m_end < adult_year or m_start > current_year:
                continue
            lord = m.lord.value.title()
            options.append(f"{lord} period ({m_start}–{m_end})")
        return (options + [skip]) if options else [skip]
    except Exception as exc:
        logger.debug("Dasha option generation failed: %s", exc)
        return [skip]


def _generate_options(answer_type: str, state: Any) -> list[str]:
    """Return MCQ choices for a given answer_type."""
    if answer_type == "yes_no":
        return list(_YES_NO_OPTIONS)
    if answer_type == "year":
        return _generate_dasha_year_options(state)
    if answer_type == "period":
        return list(_PERIOD_OPTIONS)
    if answer_type == "description":
        return list(_LIFE_PHASE_OPTIONS)
    return ["Not applicable / Skip"]


def _get_predicted_timing(question_id: str, state: Any) -> str:
    """
    Return a brief description of what the chart predicts for this event.
    Uses karaka information so users can compare against their own experience.
    """
    karakas = _TIMING_HINT.get(question_id, "")
    try:
        dasha = state.dasha_window
        if dasha is None:
            return karakas or "Chart data unavailable"
        maha_lord  = dasha.mahadasha.lord.value.title()
        maha_start = str(dasha.mahadasha.start)[:4]
        maha_end   = str(dasha.mahadasha.end)[:4]
        antar_lord = dasha.antardasha.lord.value.title() if dasha.antardasha else None
        current = (
            f"Current dasha: {maha_lord} ({maha_start}–{maha_end})"
            + (f" / {antar_lord}" if antar_lord else "")
        )
        return f"{karakas}  ·  {current}" if karakas else current
    except Exception:
        return karakas or "Chart-based prediction unavailable"


# Human-readable karaka hint shown alongside each question
_TIMING_HINT: dict[str, str] = {
    "career_start":           "Career peaks in Sun, Saturn, Mercury, Jupiter or Mars dasha",
    "career_change":          "Career shifts common in Saturn, Rahu or Mars dasha",
    "marriage_year":          "Marriage favoured in Venus, Jupiter or Moon dasha",
    "relationship_challenge": "Relationship stress rises in Saturn, Rahu, Mars or Ketu dasha",
    "first_child":            "Children favoured in Jupiter or Moon dasha",
    "wealth_gain":            "Windfalls linked to Jupiter, Venus or Mercury dasha",
    "wealth_loss":            "Financial setbacks common in Saturn, Rahu or Ketu dasha",
    "health_event":           "Health challenges rise in Saturn, Rahu, Mars or Ketu dasha",
    "foreign_move":           "Foreign moves favoured in Rahu, Jupiter or Ketu dasha",
    "education":              "Degrees completed in Jupiter, Mercury or Sun dasha",
    "family_loss":            "Losses common in Saturn, Rahu, Ketu or Mars dasha",
    "spiritual":              "Spiritual turning points in Jupiter, Ketu or Saturn dasha",
    "raj_yoga":               "Authority/recognition peaks in Sun, Jupiter or Saturn dasha",
}


# ─────────────────────────────────────────────────────────────────────────────
# Calibration result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CalibrationResult:
    """Output of the calibration process."""

    # Per-factor match scores (0–1)
    dasha_match:   float = 0.5
    natal_match:   float = 0.5
    transit_match: float = 0.5
    yoga_match:    float = 0.5
    bhava_match:   float = 0.5

    # Calibrated weights (normalised, sum to 1.0)
    weights: dict[str, float] = field(default_factory=lambda: {
        "natal":   0.20,
        "dasha":   0.30,
        "transit": 0.20,
        "yoga":    0.20,
        "bhava":   0.10,
    })

    # Summary
    overall_accuracy: float = 0.5
    answered_count:   int   = 0
    skipped_count:    int   = 0
    notes:            list[str] = field(default_factory=list)

    # Calibrated adjustments for ChartWeights (per multi-chart layer).
    # These are passed to PipelineState.chart_weights.adjust() in Phase 3.
    # Each value is a signed delta (positive = increase weight, negative = decrease).
    layer_deltas: dict[str, float] = field(default_factory=dict)

    def summary_markdown(self) -> str:
        pct = self.overall_accuracy
        if pct >= 0.70:
            acc_label = "Strong"
        elif pct >= 0.50:
            acc_label = "Moderate"
        else:
            acc_label = "Weak"

        lines = [
            f"**Calibration complete** · {self.answered_count} question(s) answered · {self.skipped_count} skipped\n",
            f"**Model–user agreement: {pct:.0%}** ({acc_label})\n",
            "**Converged weights** *(adjusted until model matched your answers)*:",
        ]
        for factor, w in self.weights.items():
            bar = "█" * int(w * 20)
            lines.append(f"- {factor.title()}: `{w:.0%}` {bar}")

        # Per-factor agreement rates
        factor_scores = {
            "Dasha":   self.dasha_match,
            "Natal":   self.natal_match,
            "Transit": self.transit_match,
            "Yoga":    self.yoga_match,
            "Bhava":   self.bhava_match,
        }
        lines.append("\n**Factor agreement rates:**")
        for name, score in factor_scores.items():
            stars = "★" * round(score * 5) + "☆" * (5 - round(score * 5))
            lines.append(f"- {name}: {stars} ({score:.0%})")

        # Per-question model-vs-user comparison
        event_notes = [n for n in self.notes if not n.startswith("Chart accuracy")]
        if event_notes:
            lines.append("\n**Model vs. your answers:**")
            for n in event_notes[:10]:
                lines.append(f"- {n}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Score answers → calibration result
# ─────────────────────────────────────────────────────────────────────────────

def score_answers(
    questions: list[CalibrationQuestion],
    answers:   list[dict],        # list of {"id": str, "answer": str|int|None, "skipped": bool}
    state:     Any = None,        # PipelineState for dasha comparison
) -> CalibrationResult:
    """
    Compare user answers against chart predictions.

    Parameters
    ----------
    questions : from generate_questions()
    answers   : user responses — each dict has "id", "answer", "skipped"
    state     : PipelineState (for dasha timing comparison)

    Returns
    -------
    CalibrationResult with calibrated weights
    """
    answer_map = {a["id"]: a for a in answers}

    factor_scores: dict[str, list[float]] = {
        "dasha": [], "natal": [], "transit": [], "yoga": [], "bhava": [],
    }
    notes: list[str] = []
    answered = 0
    skipped  = 0

    for q in questions:
        ans = answer_map.get(q.id)
        raw = ans.get("answer") if ans else None
        # Treat "Not applicable / Skip" MCQ choice as skipped
        is_skip = (
            ans is None
            or ans.get("skipped")
            or not raw
            or str(raw).strip().lower().startswith("not applicable")
        )
        if is_skip:
            skipped += 1
            continue

        answered += 1
        raw_answer = ans["answer"]
        match_score = _score_single_answer(q, raw_answer, state, notes)
        factor_scores[q.domain_factor].append(match_score)

    # Average per-factor scores (default 0.5 if unanswered)
    dasha_m   = _avg(factor_scores["dasha"],   default=0.5)
    natal_m   = _avg(factor_scores["natal"],   default=0.5)
    transit_m = _avg(factor_scores["transit"], default=0.5)
    yoga_m    = _avg(factor_scores["yoga"],    default=0.5)
    bhava_m   = _avg(factor_scores["bhava"],   default=0.5)

    overall = _avg([dasha_m, natal_m, transit_m, yoga_m, bhava_m], default=0.5)

    # Calibrate weights: accurate factors get more weight
    # Scale: match_score 0.5 = neutral (no change), 1.0 = double weight, 0.0 = half weight
    base = {"natal": 0.20, "dasha": 0.30, "transit": 0.20, "yoga": 0.20, "bhava": 0.10}
    calibrated = {
        "natal":   base["natal"]   * _weight_multiplier(natal_m),
        "dasha":   base["dasha"]   * _weight_multiplier(dasha_m),
        "transit": base["transit"] * _weight_multiplier(transit_m),
        "yoga":    base["yoga"]    * _weight_multiplier(yoga_m),
        "bhava":   base["bhava"]   * _weight_multiplier(bhava_m),
    }

    # Normalise so weights sum to 1.0
    total = sum(calibrated.values())
    if total > 0:
        calibrated = {k: round(v / total, 4) for k, v in calibrated.items()}

    if answered > 0:
        notes.insert(0,
            f"Chart accuracy based on {answered} answered events: {overall:.0%}"
        )

    return CalibrationResult(
        dasha_match=round(dasha_m, 3),
        natal_match=round(natal_m, 3),
        transit_match=round(transit_m, 3),
        yoga_match=round(yoga_m, 3),
        bhava_match=round(bhava_m, 3),
        weights=calibrated,
        overall_accuracy=round(overall, 3),
        answered_count=answered,
        skipped_count=skipped,
        notes=notes,
    )


def _score_single_answer(
    q: CalibrationQuestion,
    raw_answer: Any,
    state: Any,
    notes: list[str],
) -> float:
    """
    Score one answer against the chart prediction.
    Returns 0–1 where 1 = perfect match, 0.5 = unknown/neutral, 0 = mismatch.
    """
    if q.answer_type == "yes_no":
        # "yes" → chart predicted it (positive match for yoga/natal)
        answer_str = str(raw_answer).strip().lower()
        if answer_str in ("yes", "y", "true", "1"):
            return 0.80
        if answer_str in ("no", "n", "false", "0"):
            return 0.40
        return 0.5  # "not applicable" or other

    if q.answer_type in ("description", "period"):
        return _score_period_answer(raw_answer, q, state, notes)

    if q.answer_type == "year":
        return _score_year_answer(raw_answer, q, state, notes)

    return 0.5


def _score_year_answer(
    raw_answer: Any,
    q: CalibrationQuestion,
    state: Any,
    notes: list[str],
) -> float:
    """
    Score a year/period answer.

    Accepts two formats:
    - MCQ dasha-label format: "Saturn period (2008–2026)"  → extract lord directly
    - Legacy plain-year format: "2018"  → look up historical dasha
    """
    answer_str = str(raw_answer).strip()

    # MCQ dasha-label format: "<Lord> period (YYYY–YYYY)"
    import re as _re
    m = _re.match(r"^([A-Za-z]+)\s+period\s*\(", answer_str)
    if m:
        lord = m.group(1).lower()
        match_strength = _lord_matches_question(lord, q.id)
        label = f"{lord.title()} period"
        if match_strength == "strong":
            notes.append(f"✓ {q.id}: {label} — karaka match")
            return 0.85
        elif match_strength == "partial":
            notes.append(f"△ {q.id}: {label} — neutral lord")
            return 0.55
        else:
            notes.append(f"✗ {q.id}: {label} — weak match")
            return 0.20

    # Legacy plain-year format
    try:
        year = int(answer_str)
    except (ValueError, TypeError):
        return 0.5

    if state is None or state.chart is None:
        return 0.5

    try:
        from datetime import date as _date
        from vedic_astro.engines.dasha_engine import compute_maha_dashas
        from vedic_astro.engines.natal_engine import PlanetName

        moon_lon = state.chart.planets[PlanetName.MOON].longitude
        b = state.request.birth
        birth_dt = _date(b.year, b.month, b.day)

        all_mahas = compute_maha_dashas(moon_lon, birth_dt)
        event_date = _date(year, 6, 15)

        active_maha = next((m for m in all_mahas if m.start <= event_date < m.end), None)
        if active_maha is None:
            return 0.5

        lord = active_maha.lord.value.lower()
        match_strength = _lord_matches_question(lord, q.id)

        if match_strength == "strong":
            notes.append(f"✓ {q.id}: {year} in {lord.title()} Mahadasha — karaka match")
            return 0.85
        elif match_strength == "partial":
            notes.append(f"△ {q.id}: {year} in {lord.title()} Mahadasha — neutral lord")
            return 0.55
        else:
            notes.append(f"✗ {q.id}: {year} in {lord.title()} Mahadasha — weak match")
            return 0.20

    except Exception:
        return 0.5


# Karaka (significator) lords per question — strong karaka = high match score
_KARAKA_LORDS: dict[str, list[str]] = {
    "career_start":          ["sun", "saturn", "mercury", "jupiter", "mars"],
    "career_change":         ["saturn", "rahu", "mars", "sun", "ketu"],
    "marriage_year":         ["venus", "jupiter", "moon"],
    "relationship_challenge":["saturn", "rahu", "mars", "ketu"],
    "first_child":           ["jupiter", "moon", "venus"],
    "wealth_gain":           ["jupiter", "venus", "mercury", "moon"],
    "wealth_loss":           ["saturn", "rahu", "ketu", "mars"],
    "health_event":          ["saturn", "rahu", "mars", "ketu", "sun"],
    "foreign_move":          ["rahu", "jupiter", "ketu", "moon"],
    "education":             ["jupiter", "mercury", "sun", "saturn"],
    "family_loss":           ["saturn", "rahu", "ketu", "mars", "moon"],
    "spiritual":             ["jupiter", "ketu", "saturn", "moon"],
    "raj_yoga":              ["sun", "jupiter", "mars", "saturn"],
    "current_period":        [],  # scored separately
    "life_phase":            [],  # scored separately
}


def _lord_matches_question(lord: str, question_id: str) -> str:
    """Return 'strong', 'partial', or 'weak' based on karaka match."""
    karakas = _KARAKA_LORDS.get(question_id, [])
    if not karakas:
        return "partial"   # no mapping → neutral
    if lord in karakas:
        return "strong"
    # Neutral lords (Sun/Moon/Mercury broadly relevant to most domains)
    neutral = {"sun", "moon", "jupiter"}
    if lord in neutral:
        return "partial"
    return "weak"


def _score_period_answer(
    raw_answer: Any,
    q: CalibrationQuestion,
    state: Any,
    notes: list[str],
) -> float:
    """Score qualitative period descriptions against current dasha prediction."""
    answer_str = str(raw_answer).strip().lower()

    if state is None or state.score is None:
        return 0.5

    score_val = state.score.final_score
    interp    = state.score.interpretation.lower() if state.score else ""

    positive_words  = {"growth", "expansion", "success", "great", "good", "excellent", "building", "peak"}
    negative_words  = {"challenging", "difficult", "hard", "loss", "struggle", "bad", "tough", "transition"}
    neutral_words   = {"stable", "steady", "ok", "okay", "average", "moderate", "consolidation"}

    is_positive  = any(w in answer_str for w in positive_words)
    is_negative  = any(w in answer_str for w in negative_words)
    is_neutral   = any(w in answer_str for w in neutral_words)

    chart_positive = score_val >= 0.55
    chart_negative = score_val < 0.40

    if is_positive and chart_positive:
        return 0.85
    if is_negative and chart_negative:
        return 0.85
    if is_neutral and not chart_positive and not chart_negative:
        return 0.75
    if (is_positive and chart_negative) or (is_negative and chart_positive):
        return 0.20
    return 0.50


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _avg(values: list[float], default: float = 0.5) -> float:
    return sum(values) / len(values) if values else default


def _weight_multiplier(match_score: float) -> float:
    """
    Convert a 0–1 match score to a weight multiplier.
    match=1.0 → 2.0x (highly accurate, increase weight)
    match=0.5 → 1.0x (neutral, no change)
    match=0.0 → 0.5x (inaccurate, halve weight)
    """
    # Linear interpolation: 0→0.5, 0.5→1.0, 1.0→2.0
    if match_score >= 0.5:
        return 1.0 + (match_score - 0.5) * 2.0  # 1.0 → 2.0
    else:
        return 0.5 + match_score  # 0.5 → 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Convergence-based calibration (new primary path)
# ─────────────────────────────────────────────────────────────────────────────

# Dignity scores for natal planet strength in predictions
_DIGNITY_SCORE: dict[str, float] = {
    "exalted":      1.00,
    "moolatrikona": 0.85,
    "own_sign":     0.80,
    "neutral":      0.50,
    "debilitated":  0.20,
}

# Sentiment buckets for period/description questions
_PERIOD_SENTIMENT: list[tuple[float, str]] = [
    (0.75, "Thriving — exceptional growth and gains"),
    (0.60, "Positive — steady progress with minor setbacks"),
    (0.45, "Mixed — equal highs and lows"),
    (0.30, "Challenging — significant difficulties"),
    (0.00, "Very difficult — major losses or crises"),
]

_LIFE_PHASE_THRESHOLDS: list[tuple[float, str]] = [
    (0.70, "Peak — at my most successful and active"),
    (0.55, "Building — establishing career, relationships, foundation"),
    (0.40, "Transition — going through major changes"),
    (0.00, "Consolidation — slowing down, reflecting, wisdom phase"),
]


def _natal_dignity_of_lord(lord: str, state: Any) -> float:
    """Return natal dignity score (0–1) for a planet from chart state."""
    if state is None or state.chart is None:
        return 0.5
    try:
        from vedic_astro.rules.bphs_rules import (
            EXALTATION_SIGN, DEBILITATION_SIGN, MOOLATRIKONA, OWN_SIGNS
        )
        from vedic_astro.engines.natal_engine import PlanetName
        lord_key = lord.lower()
        for pname, pos in state.chart.planets.items():
            if pname.value.lower() == lord_key:
                sign = pos.sign if isinstance(pos.sign, str) else str(pos.sign)
                planet_title = lord.title()
                if sign == EXALTATION_SIGN.get(planet_title):
                    return _DIGNITY_SCORE["exalted"]
                if sign == DEBILITATION_SIGN.get(planet_title):
                    return _DIGNITY_SCORE["debilitated"]
                if sign == MOOLATRIKONA.get(planet_title):
                    return _DIGNITY_SCORE["moolatrikona"]
                if sign in OWN_SIGNS.get(planet_title, []):
                    return _DIGNITY_SCORE["own_sign"]
                return _DIGNITY_SCORE["neutral"]
    except Exception as exc:
        logger.debug("Natal dignity lookup failed: %s", exc)
    return 0.5


def _karaka_strength_score(lord: str, question_id: str) -> float:
    """Numeric karaka strength: strong=1.0, partial=0.5, weak=0.1."""
    match = _lord_matches_question(lord.lower(), question_id)
    return {"strong": 1.0, "partial": 0.5, "weak": 0.1}[match]


def predict_answer(q: CalibrationQuestion, state: Any, weights: dict[str, float]) -> str:
    """
    Deterministic chart-based prediction of the MCQ answer for question q.

    For year questions: scores each dasha period in the user's adult life as
        score = karaka_strength × weights["dasha"]
              + natal_dignity × weights["natal"]
    and returns the label of the highest-scoring period.

    For yes_no / period / description: uses score.final_score mapped to buckets.
    Falls back to "Not applicable / Skip" when chart data is missing.
    """
    skip = "Not applicable / Skip"

    if q.answer_type == "year":
        return _predict_year_period(q, state, weights)

    if q.answer_type == "yes_no":
        return _predict_yes_no(q, state, weights)

    if q.answer_type == "period":
        return _predict_period(state, weights)

    if q.answer_type == "description":
        return _predict_life_phase(state, weights)

    return skip


def _predict_year_period(q: CalibrationQuestion, state: Any, weights: dict) -> str:
    """Score each adult dasha period and return the label of the highest-scoring one."""
    skip = "Not applicable / Skip"
    try:
        from datetime import date as _date
        from vedic_astro.engines.dasha_engine import compute_maha_dashas
        from vedic_astro.engines.natal_engine import PlanetName

        moon_lon = state.chart.planets[PlanetName.MOON].longitude
        b = state.request.birth
        birth_dt = _date(b.year, b.month, b.day)
        adult_year    = b.year + 15
        current_year  = _date.today().year + 5

        all_mahas = compute_maha_dashas(moon_lon, birth_dt)
        best_label = skip
        best_score = -1.0

        dasha_w = weights.get("dasha", 0.30)
        natal_w = weights.get("natal", 0.20)

        for m in all_mahas:
            if m.end.year < adult_year or m.start.year > current_year:
                continue
            lord = m.lord.value
            karaka = _karaka_strength_score(lord, q.id)
            dignity = _natal_dignity_of_lord(lord, state)
            score = karaka * dasha_w + dignity * natal_w
            if score > best_score:
                best_score = score
                best_label = f"{lord.title()} period ({m.start.year}–{m.end.year})"

        return best_label
    except Exception as exc:
        logger.debug("Year period prediction failed: %s", exc)
        return skip


def _predict_yes_no(q: CalibrationQuestion, state: Any, weights: dict) -> str:
    """Predict Yes/No based on yoga presence and yoga weight."""
    try:
        yoga_w = weights.get("yoga", 0.20)
        if state.yoga_bundle:
            yoga_names = [y.name.lower() for y in state.yoga_bundle.active_yogas]
            # raj_yoga question: check for raja/raj yoga presence
            if q.id == "raj_yoga" and any("raj" in n or "raja" in n for n in yoga_names):
                # If yoga is present AND we trust yoga factor sufficiently → Yes
                return "Yes" if yoga_w >= 0.12 else "No"
        return "No"
    except Exception as exc:
        logger.debug("Yes/no prediction failed: %s", exc)
        return "Not applicable / Skip"


def _predict_period(state: Any, weights: dict) -> str:
    """Map the chart's final score to a sentiment bucket."""
    try:
        if state.score is None:
            return "Mixed — equal highs and lows"
        score = state.score.final_score
        for threshold, label in _PERIOD_SENTIMENT:
            if score >= threshold:
                return label
    except Exception as exc:
        logger.debug("Period prediction failed: %s", exc)
    return "Mixed — equal highs and lows"


def _predict_life_phase(state: Any, weights: dict) -> str:
    """Map chart score to life phase."""
    try:
        if state.score is None:
            return "Transition — going through major changes"
        score = state.score.final_score
        for threshold, label in _LIFE_PHASE_THRESHOLDS:
            if score >= threshold:
                return label
    except Exception as exc:
        logger.debug("Life phase prediction failed: %s", exc)
    return "Transition — going through major changes"


def _normalize_weights(w: dict[str, float]) -> dict[str, float]:
    total = sum(w.values())
    if total <= 0:
        return w
    return {k: round(v / total, 4) for k, v in w.items()}


def _adjust_weights(
    weights: dict[str, float],
    factor: str,
    user_ans_karaka_consistent: bool,
    step: float = 0.04,
) -> dict[str, float]:
    """
    Nudge weights toward or away from `factor` based on whether the user's
    answer was karaka-consistent with that factor's prediction.

    Consistent (factor predicted something close to truth): increase factor weight.
    Inconsistent (factor's model of the world doesn't match reality):  decrease it.
    """
    w = dict(weights)
    if user_ans_karaka_consistent:
        # Increase this factor — its rules ARE correct for this person
        w[factor] = min(0.55, w[factor] + step)
    else:
        # Decrease this factor — its rules DON'T fit this person
        w[factor] = max(0.04, w[factor] - step)
    return _normalize_weights(w)


@dataclass
class QuestionResult:
    """Per-question outcome from the convergence loop."""
    question_id:   str
    question_text: str
    user_answer:   str
    model_answer:  str
    matched:       bool
    iterations_to_match: int   # 0 = matched on first try, -1 = never converged


def calibrate_convergence(
    questions: list[CalibrationQuestion],
    user_answers: list[dict],
    state: Any,
    max_iter: int = 10,
) -> CalibrationResult:
    """
    Primary calibration path.

    For each answered question:
    1. The model predicts an answer from the chart + current weights.
    2. Compare with the user's answer.
    3. If they match → weights are validated for this factor.
    4. If they differ → adjust the factor weight and re-predict.
    5. Repeat until all answered questions match or max_iter is reached.

    Returns a CalibrationResult with converged weights and a per-question log
    stored in .notes.
    """
    _DEFAULT_WEIGHTS = {
        "natal": 0.20, "dasha": 0.30, "transit": 0.20,
        "yoga": 0.20, "bhava": 0.10,
    }
    weights = dict(_DEFAULT_WEIGHTS)

    answer_map = {a["id"]: a for a in user_answers}

    # Filter to actually answered (non-skip) questions
    answered: list[tuple[CalibrationQuestion, str]] = []
    skipped_count = 0
    for q in questions:
        ans = answer_map.get(q.id)
        if not ans:
            skipped_count += 1
            continue
        raw = ans.get("answer") or ""
        if (
            ans.get("skipped")
            or not raw
            or str(raw).strip().lower().startswith("not applicable")
        ):
            skipped_count += 1
            continue
        answered.append((q, str(raw).strip()))

    if not answered:
        result = CalibrationResult(answered_count=0, skipped_count=skipped_count)
        result.notes = ["No answers provided — using default weights."]
        return result

    question_results: list[QuestionResult] = []

    # Per-question convergence loop (each question gets its own weight adjustment)
    for q, user_ans in answered:
        iters_to_match = -1
        for iteration in range(max_iter + 1):
            model_pred = predict_answer(q, state, weights)
            if model_pred == user_ans:
                iters_to_match = iteration
                break
            if iteration < max_iter:
                # Determine if user's answer is karaka-consistent with this factor
                # For year questions: check karaka match of user's chosen lord
                karaka_consistent = False
                if q.answer_type == "year":
                    import re as _re
                    m = _re.match(r"^([A-Za-z]+)\s+period", user_ans)
                    if m:
                        user_lord = m.group(1).lower()
                        karaka_consistent = (
                            _lord_matches_question(user_lord, q.id) in ("strong", "partial")
                        )
                elif q.answer_type == "yes_no":
                    karaka_consistent = (user_ans.lower() == "yes")
                elif q.answer_type in ("period", "description"):
                    # positive answer → chart score should be high → trust current factors
                    karaka_consistent = any(
                        w in user_ans.lower()
                        for w in ("thriving", "positive", "peak", "building")
                    )

                weights = _adjust_weights(weights, q.domain_factor, karaka_consistent)

        question_results.append(QuestionResult(
            question_id=q.id,
            question_text=q.text,
            user_answer=user_ans,
            model_answer=predict_answer(q, state, weights),
            matched=(iters_to_match >= 0),
            iterations_to_match=iters_to_match,
        ))

    # Compute final match statistics
    matched = [r for r in question_results if r.matched]
    overall_accuracy = len(matched) / len(question_results) if question_results else 0.5

    # Build per-factor match rates
    factor_results: dict[str, list[bool]] = {f: [] for f in weights}
    for r, (q, _) in zip(question_results, answered):
        factor_results[q.domain_factor].append(r.matched)

    def _factor_acc(lst: list[bool]) -> float:
        return sum(lst) / len(lst) if lst else 0.5

    dasha_m   = _factor_acc(factor_results["dasha"])
    natal_m   = _factor_acc(factor_results["natal"])
    transit_m = _factor_acc(factor_results["transit"])
    yoga_m    = _factor_acc(factor_results["yoga"])
    bhava_m   = _factor_acc(factor_results["bhava"])

    # Build human-readable notes
    notes: list[str] = []
    for r in question_results:
        icon = "✓" if r.matched else "✗"
        iters = f" (converged in {r.iterations_to_match} steps)" if r.matched and r.iterations_to_match > 0 else ""
        no_conv = " (did not converge)" if not r.matched else ""
        notes.append(
            f"{icon} [{r.question_id}] Model: *{r.model_answer}* | You: *{r.user_answer}*"
            f"{iters}{no_conv}"
        )

    # Map scoring weights → ChartWeights layer deltas.
    # The delta = calibrated_weight − default_weight, clamped to ±0.15.
    # Mapping: dasha→vimshottari, natal→d1_natal, transit→transit, yoga→yogas
    _FACTOR_TO_LAYER = {
        "dasha":   "vimshottari",
        "natal":   "d1_natal",
        "transit": "transit",
        "yoga":    "yogas",
        "bhava":   "special_lagnas",
    }
    _DEFAULTS_SCORING = {"natal": 0.20, "dasha": 0.30, "transit": 0.20, "yoga": 0.20, "bhava": 0.10}
    layer_deltas = {}
    for factor, layer in _FACTOR_TO_LAYER.items():
        delta = round(weights.get(factor, _DEFAULTS_SCORING[factor]) - _DEFAULTS_SCORING[factor], 4)
        if abs(delta) > 0.001:
            layer_deltas[layer] = max(-0.15, min(0.15, delta))

    return CalibrationResult(
        dasha_match=round(dasha_m, 3),
        natal_match=round(natal_m, 3),
        transit_match=round(transit_m, 3),
        yoga_match=round(yoga_m, 3),
        bhava_match=round(bhava_m, 3),
        weights=weights,
        overall_accuracy=round(overall_accuracy, 3),
        answered_count=len(answered),
        skipped_count=skipped_count,
        notes=notes,
        layer_deltas=layer_deltas,
    )
