"""
calibration.py — Chart-aware calibration question generation and weight adjustment.

Purpose
-------
After computing a natal chart (Phase 1), the system generates 10 personalised
questions about past life events. The user's answers are compared against what
the chart's dashas/houses predicted. The match scores calibrate the six scoring
weights so that Phase 3 predictions are tailored to how accurate this chart has
proven to be for this specific person.

Flow
----
1. generate_questions(state) → list[CalibrationQuestion]
   Selects the 10 most chart-relevant questions from a bank of ~40.

2. score_answers(questions, answers) → CalibrationResult
   Computes per-factor match scores (0–1) and adjusted weights.

3. apply_calibration(scorer_weights, calibration) → ScoringWeights
   Returns updated ScoringWeights for use in Phase 3.

Usage
-----
    from vedic_astro.agents.calibration import generate_questions, score_answers

    questions = generate_questions(pipeline_state)
    # Show to user, collect answers …
    result = score_answers(questions, user_answers)
    # result.weights → use in scorer
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
    except Exception:
        pass
    return features


def _question_is_relevant(question: dict, features: dict) -> bool:
    trigger = question.get("trigger", "any")
    if trigger == "any":
        return True
    return bool(features.get(trigger, False))


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

    def summary_markdown(self) -> str:
        # Accuracy indicator
        pct = self.overall_accuracy
        if pct >= 0.70:
            acc_label = "Strong"
        elif pct >= 0.50:
            acc_label = "Moderate"
        else:
            acc_label = "Weak"

        lines = [
            f"**Calibration complete** · {self.answered_count} question(s) scored\n",
            f"**Chart accuracy: {pct:.0%}** ({acc_label})\n",
            "**Calibrated weights:**",
        ]
        for factor, w in self.weights.items():
            bar = "█" * int(w * 20)
            lines.append(f"- {factor.title()}: `{w:.0%}` {bar}")

        # Per-factor match scores
        factor_scores = {
            "Dasha":   self.dasha_match,
            "Natal":   self.natal_match,
            "Transit": self.transit_match,
            "Yoga":    self.yoga_match,
            "Bhava":   self.bhava_match,
        }
        lines.append("\n**Factor match scores:**")
        for name, score in factor_scores.items():
            stars = "★" * round(score * 5) + "☆" * (5 - round(score * 5))
            lines.append(f"- {name}: {stars} ({score:.0%})")

        # Significant notes only (skip the redundant accuracy repeat)
        event_notes = [n for n in self.notes if not n.startswith("Chart accuracy")]
        if event_notes:
            lines.append("\n**Event matches:**")
            for n in event_notes[:6]:
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
        if ans is None or ans.get("skipped") or not ans.get("answer"):
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
        return 0.40  # "no" means chart prediction may not have manifested

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
    """Compare a year answer against the historically active dasha at that year."""
    try:
        year = int(str(raw_answer).strip())
    except (ValueError, TypeError):
        return 0.5   # can't parse — neutral

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
        event_date = _date(year, 6, 15)   # approximate mid-year

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
