"""
scorer.py — Weighted astrological scoring system.

Architecture
------------
The ``WeightedScorer`` takes an ``AstroFeatures`` object and produces a
``ScoreBreakdown`` with five component scores plus a weighted composite.

Component scores (all 0.0–1.0)
-------------------------------
1. ``natal_strength``    — Dignity + house placement of query-domain planets.
2. ``dasha_activation``  — Dasha lord's natal strength + mutual relationship.
3. ``transit_trigger``   — Gochara composite, weighted by planet importance.
4. ``yoga_support``      — Active yoga strengths filtered by domain relevance.
5. ``dosha_penalty``     — Active doshas filtered by domain relevance (subtracted).

Final score formula
-------------------
    final = (
        W_natal × natal_strength
      + W_dasha × dasha_activation
      + W_transit × transit_trigger
      + W_yoga × yoga_support
      − W_dosha × dosha_penalty
    ) / total_positive_weight

Global default weights: natal=0.35, dasha=0.30, transit=0.25, yoga=0.10

Domain-specific weights
-----------------------
Different astrological queries require different emphasis.  For career
questions the 10th lord and D10 matter more; for marriage the 7th lord
and D9 matter more.  ``DomainConfig`` encodes these adjustments.

Interpretation labels
---------------------
    final ≥ 0.75  → "very_strong_positive"
    0.60 – 0.74   → "strong_positive"
    0.50 – 0.59   → "moderate_positive"
    0.40 – 0.49   → "mixed"
    0.30 – 0.39   → "challenging"
    < 0.30        → "very_challenging"

Usage
-----
    from vedic_astro.learning.scorer import WeightedScorer
    scorer = WeightedScorer()
    result = scorer.score(features, domain="career")
    print(result.final_score, result.interpretation)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from vedic_astro.learning.feature_builder import AstroFeatures


# ─────────────────────────────────────────────────────────────────────────────
# Expert priors
# ─────────────────────────────────────────────────────────────────────────────

# Dignity strength multipliers (classical Parashari approximation)
DIGNITY_SCORES: dict[str, float] = {
    "exalted":      1.00,
    "moolatrikona": 0.85,
    "own":          0.75,
    "friend":       0.55,
    "neutral":      0.40,
    "enemy":        0.20,
    "debilitated":  0.00,
}

# Natural benefic/malefic influence on houses (0 = neutral, +0.1 = benefic bonus)
_BENEFIC_PLANETS  = {"jupiter", "venus", "moon", "mercury"}
_MALEFIC_PLANETS  = {"sun", "mars", "saturn", "rahu", "ketu"}

# Kendra (1,4,7,10) and Trikona (1,5,9) house bonuses for natal placement
_KENDRA_HOUSES    = {1, 4, 7, 10}
_TRIKONA_HOUSES   = {1, 5, 9}
_DUSTHANA_HOUSES  = {6, 8, 12}

# Transit planet importance weights (outer planets matter more for timing)
TRANSIT_PLANET_IMPORTANCE: dict[str, float] = {
    "saturn":  0.28,
    "jupiter": 0.24,
    "rahu":    0.18,
    "ketu":    0.14,
    "mars":    0.07,
    "sun":     0.04,
    "venus":   0.02,
    "mercury": 0.02,
    "moon":    0.01,
}

# Yoga domain relevance map: domain → set of relevant yoga names (partial match)
_YOGA_DOMAIN_RELEVANCE: dict[str, set[str]] = {
    "career":       {"raj_yoga", "mahapurusha", "ruchaka", "bhadra", "shasha", "dhana_yoga"},
    "marriage":     {"raj_yoga", "malavya", "hamsa", "gajakesari"},
    "wealth":       {"dhana_yoga", "raj_yoga", "hamsa", "gajakesari"},
    "health":       {"hamsa", "bhadra"},
    "spirituality": {"hamsa", "gajakesari"},
    "children":     {"hamsa", "raj_yoga"},
    "general":      set(),   # all yogas count
}

# Dosha domain relevance map: domain → set of relevant dosha names
_DOSHA_DOMAIN_RELEVANCE: dict[str, set[str]] = {
    "career":       {"kemdrum_yoga", "guru_chandala_yoga", "shrapit_dosha"},
    "marriage":     {"mangal_dosha", "kala_sarpa_dosha", "kemdrum_yoga"},
    "wealth":       {"kala_sarpa_dosha", "shrapit_dosha"},
    "health":       {"grahan_dosha", "kala_sarpa_dosha"},
    "spirituality": {"guru_chandala_yoga"},
    "children":     {"kala_sarpa_dosha", "mangal_dosha"},
    "general":      set(),   # all doshas count
}

# Domain → key houses to emphasise (7th for marriage, 10th for career, etc.)
_DOMAIN_KEY_HOUSES: dict[str, list[int]] = {
    "career":       [10, 6, 2, 1],
    "marriage":     [7, 2, 11, 1],
    "wealth":       [2, 11, 8, 5],
    "health":       [1, 6, 8, 12],
    "spirituality": [9, 12, 5, 1],
    "children":     [5, 9, 1],
    "general":      [1, 4, 7, 10, 5, 9],   # Kendra + Trikona
}

# Domain → key planets to emphasise
_DOMAIN_KEY_PLANETS: dict[str, list[str]] = {
    "career":       ["sun", "saturn", "mercury", "mars"],
    "marriage":     ["venus", "jupiter", "moon"],
    "wealth":       ["jupiter", "venus", "mercury"],
    "health":       ["sun", "moon", "mars"],
    "spirituality": ["jupiter", "ketu", "saturn"],
    "children":     ["jupiter", "moon", "sun"],
    "general":      [],  # all planets
}


# ─────────────────────────────────────────────────────────────────────────────
# Scoring weights
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScoringWeights:
    """
    Global weight configuration for the weighted scorer.

    Weights are normalised internally so they don't need to sum to 1.
    """
    natal_weight:   float = 0.35
    dasha_weight:   float = 0.30
    transit_weight: float = 0.25
    yoga_weight:    float = 0.10

    # Sade Sati severity multiplier applied to transit score (additive penalty)
    sadesati_penalty: float = 0.15

    # Retrograde dasha lord penalty
    retrograde_penalty: float = 0.10

    # Combust planet penalty (applied to natal score)
    combust_penalty: float = 0.08


# ─────────────────────────────────────────────────────────────────────────────
# Score result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScoreBreakdown:
    """
    Full scoring result with component scores and interpretation.

    All component scores are in the range [0.0, 1.0].
    ``dosha_penalty`` is a deduction (positive value = penalty applied).
    ``final_score``   is the weighted composite (clamped to [0.0, 1.0]).
    """
    domain: str
    natal_strength:    float
    dasha_activation:  float
    transit_trigger:   float
    yoga_support:      float
    dosha_penalty:     float
    final_score:       float
    interpretation:    str
    notes: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (
            f"[{self.domain}] natal={self.natal_strength:.2f} "
            f"dasha={self.dasha_activation:.2f} transit={self.transit_trigger:.2f} "
            f"yoga={self.yoga_support:.2f} dosha_penalty={self.dosha_penalty:.2f} "
            f"→ final={self.final_score:.2f} ({self.interpretation})"
        )


def _interpret(score: float) -> str:
    if score >= 0.75: return "very_strong_positive"
    if score >= 0.60: return "strong_positive"
    if score >= 0.50: return "moderate_positive"
    if score >= 0.40: return "mixed"
    if score >= 0.30: return "challenging"
    return "very_challenging"


# ─────────────────────────────────────────────────────────────────────────────
# Weighted scorer
# ─────────────────────────────────────────────────────────────────────────────

class WeightedScorer:
    """
    Domain-aware multi-factor Vedic astrology scorer.

    Usage
    -----
        scorer = WeightedScorer()
        result = scorer.score(features, domain="career")
        print(result.final_score, result.interpretation)
    """

    def __init__(self, weights: Optional[ScoringWeights] = None) -> None:
        self._w = weights or ScoringWeights()

    # ── Public API ────────────────────────────────────────────────────────

    def score(
        self,
        features: AstroFeatures,
        domain: str = "general",
    ) -> ScoreBreakdown:
        """
        Compute a weighted score for *features* in the given *domain*.

        Parameters
        ----------
        features : AstroFeatures from FeatureBuilder.
        domain   : Query domain: "career"|"marriage"|"wealth"|"health"|
                   "spirituality"|"children"|"general".

        Returns
        -------
        ScoreBreakdown
        """
        domain = domain.lower()
        notes: list[str] = []

        natal   = self._score_natal_strength(features, domain, notes)
        dasha   = self._score_dasha_activation(features, domain, notes)
        transit = self._score_transit_trigger(features, notes)
        yoga    = self._score_yoga_support(features, domain, notes)
        dosha   = self._score_dosha_penalty(features, domain, notes)

        w = self._w
        numerator = (
            w.natal_weight   * natal
          + w.dasha_weight   * dasha
          + w.transit_weight * transit
          + w.yoga_weight    * yoga
        )
        denominator = w.natal_weight + w.dasha_weight + w.transit_weight + w.yoga_weight

        raw_score = numerator / denominator if denominator > 0 else 0.5
        # Subtract dosha penalty (dosha_penalty already normalised to [0,1])
        final = max(0.0, min(1.0, raw_score - dosha * 0.20))

        return ScoreBreakdown(
            domain=domain,
            natal_strength=round(natal, 3),
            dasha_activation=round(dasha, 3),
            transit_trigger=round(transit, 3),
            yoga_support=round(yoga, 3),
            dosha_penalty=round(dosha, 3),
            final_score=round(final, 3),
            interpretation=_interpret(final),
            notes=notes,
        )

    # ── Component scorers ─────────────────────────────────────────────────

    def _score_natal_strength(
        self,
        f: AstroFeatures,
        domain: str,
        notes: list[str],
    ) -> float:
        """
        Assess natal planet dignity and house placement for the domain.

        Steps:
        1. Identify key planets and houses for the domain.
        2. Score each key planet: dignity score × house bonus × combust penalty.
        3. Penalise lagna lord if in dusthana.
        4. Average across key planets.
        """
        key_planets = _DOMAIN_KEY_PLANETS.get(domain) or list(f.planet_signs.keys())
        key_houses  = set(_DOMAIN_KEY_HOUSES.get(domain, [1, 4, 7, 10]))

        scores = []
        for planet in key_planets:
            dignity = f.planet_dignities.get(planet, "neutral")
            house   = f.planet_houses.get(planet, 0)

            d_score = DIGNITY_SCORES.get(dignity, 0.40)

            # House bonus
            if house in _KENDRA_HOUSES:
                house_mult = 1.15
            elif house in _TRIKONA_HOUSES:
                house_mult = 1.10
            elif house in _DUSTHANA_HOUSES:
                house_mult = 0.75
            else:
                house_mult = 1.0

            # Domain key house bonus
            if house in key_houses:
                house_mult *= 1.10

            # Combust penalty
            combust_mult = (1.0 - self._w.combust_penalty) if f.planet_is_combust.get(planet) else 1.0

            p_score = min(1.0, d_score * house_mult * combust_mult)
            scores.append(p_score)

            if dignity == "debilitated":
                notes.append(f"{planet.title()} debilitated — weakens {domain} prospects")
            elif dignity == "exalted" and house in key_houses:
                notes.append(f"{planet.title()} exalted in house {house} — strong {domain} indicator")

        if not scores:
            return 0.5

        # Lagna lord penalty
        lagna_lord = _get_lagna_lord(f.lagna_sign)
        if lagna_lord:
            ll_house = f.planet_houses.get(lagna_lord, 0)
            if ll_house in _DUSTHANA_HOUSES:
                notes.append(f"Lagna lord in {ll_house}th (dusthana) — overall constitution weakened")
                return max(0.0, sum(scores) / len(scores) - 0.08)

        return sum(scores) / len(scores)

    def _score_dasha_activation(
        self,
        f: AstroFeatures,
        domain: str,
        notes: list[str],
    ) -> float:
        """
        Assess whether the active dasha amplifies the domain.

        Checks:
        - Maha lord dignity (natal placement quality).
        - Maha/Antar lord mutual friendship.
        - Whether dasha lords rule houses relevant to the domain.
        - Timing (early periods are more potent than ending periods).
        """
        if not f.maha_lord:
            return 0.5   # no dasha data

        maha_dignity = f.maha_lord_dignity
        antar_dignity = f.antar_lord_dignity

        maha_score  = DIGNITY_SCORES.get(maha_dignity, 0.40)
        antar_score = DIGNITY_SCORES.get(antar_dignity, 0.40) if f.antar_lord else 0.5

        # Maha lord house placement
        maha_house = f.maha_lord_house
        if maha_house in _KENDRA_HOUSES | _TRIKONA_HOUSES:
            maha_score = min(1.0, maha_score + 0.12)
        elif maha_house in _DUSTHANA_HOUSES:
            maha_score = max(0.0, maha_score - 0.12)

        # Friendship bonus
        friendship_mult = 1.08 if f.dasha_lords_are_friends else 1.0

        # Domain-house rulership bonus
        key_houses = set(_DOMAIN_KEY_HOUSES.get(domain, []))
        maha_rules_key = bool(set(f.maha_lord_rules_houses) & key_houses)
        antar_rules_key = bool(set(f.antar_lord_rules_houses) & key_houses)

        domain_bonus = 0.0
        if maha_rules_key:
            domain_bonus += 0.10
            notes.append(f"Maha lord ({f.maha_lord}) rules {domain} houses — timing favourable")
        if antar_rules_key:
            domain_bonus += 0.05

        # Retrograde penalty
        maha_retro = f.planet_is_retrograde.get(f.maha_lord, False)
        retro_pen = self._w.retrograde_penalty if maha_retro else 0.0

        # Timing: dasha early vs late (very late dashas may feel like tail-off)
        timing_mult = 1.0
        if f.maha_elapsed_fraction < 0.2:
            timing_mult = 1.05  # just beginning — more potent
        elif f.maha_elapsed_fraction > 0.85:
            timing_mult = 0.95  # near end

        score = (0.60 * maha_score + 0.40 * antar_score) * friendship_mult * timing_mult
        score = min(1.0, score + domain_bonus - retro_pen)
        return max(0.0, score)

    def _score_transit_trigger(
        self,
        f: AstroFeatures,
        notes: list[str],
    ) -> float:
        """
        Compute weighted gochara (transit) trigger score.

        Weights outer planets more heavily (Saturn/Jupiter/Rahu/Ketu).
        Applies Sade Sati penalty when active.
        """
        if not f.gochara_strengths:
            return 0.5

        weighted_sum = 0.0
        total_weight = 0.0
        for planet, strength in f.gochara_strengths.items():
            importance = TRANSIT_PLANET_IMPORTANCE.get(planet, 0.01)
            weighted_sum += importance * strength
            total_weight += importance

        base = weighted_sum / total_weight if total_weight > 0 else 0.5

        # Sade Sati penalty
        if f.sadesati_active:
            phase = f.sadesati_phase or "peak"
            penalty = {"peak": 0.15, "rising": 0.10, "setting": 0.08}.get(phase, 0.10)
            base = max(0.0, base - penalty)
            notes.append(f"Sade Sati {phase} phase — Saturn transit over/near natal Moon")

        # Jupiter favourable → bonus
        jup_fav = f.gochara_favorable.get("jupiter", False)
        if jup_fav:
            base = min(1.0, base + 0.05)

        return base

    def _score_yoga_support(
        self,
        f: AstroFeatures,
        domain: str,
        notes: list[str],
    ) -> float:
        """
        Score active yogas filtered to those relevant for the domain.

        Doshas are scored separately (see _score_dosha_penalty).
        """
        if not f.active_yoga_names:
            return 0.40  # neutral when no data

        relevant = _YOGA_DOMAIN_RELEVANCE.get(domain, set())

        if relevant:
            # Score only domain-relevant yogas
            relevant_names = [
                y for y in f.active_yoga_names
                if any(r.lower() in y.lower() for r in relevant)
            ]
            all_names = relevant_names or f.active_yoga_names
        else:
            all_names = f.active_yoga_names

        if not all_names:
            return 0.40

        strengths = [f.yoga_strengths.get(y, 0.5) for y in all_names]
        avg = sum(strengths) / len(strengths)

        # Bonus if ≥2 yogas present
        count_bonus = min(0.10, len(strengths) * 0.03)

        score = min(1.0, avg + count_bonus)
        if relevant_names:
            notes.append(
                f"{len(relevant_names)} domain-relevant yoga(s): {', '.join(relevant_names[:3])}"
            )
        return score

    def _score_dosha_penalty(
        self,
        f: AstroFeatures,
        domain: str,
        notes: list[str],
    ) -> float:
        """
        Compute aggregate dosha penalty (returned as positive number).

        The caller subtracts this from the final score.
        """
        if not f.active_dosha_names:
            return 0.0

        relevant = _DOSHA_DOMAIN_RELEVANCE.get(domain, set())

        if relevant:
            domain_doshas = [
                d for d in f.active_dosha_names
                if any(r.lower() in d.lower() for r in relevant)
            ]
        else:
            domain_doshas = f.active_dosha_names

        if not domain_doshas:
            return 0.0

        severities = [f.dosha_severities.get(d, 0.5) for d in domain_doshas]
        # Worst dosha has highest weight (not average — the most severe matters most)
        worst = max(severities)
        avg   = sum(severities) / len(severities)
        penalty = 0.60 * worst + 0.40 * avg

        notes.append(
            f"Active dosha(s) for {domain}: {', '.join(domain_doshas[:3])} "
            f"(worst severity={worst:.2f})"
        )
        return min(1.0, penalty)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: lagna lord
# ─────────────────────────────────────────────────────────────────────────────

def _get_lagna_lord(lagna_sign: int) -> Optional[str]:
    """Return the lagna lord's planet.value string."""
    try:
        from vedic_astro.engines.natal_engine import SIGN_LORDS
        lord = SIGN_LORDS.get(lagna_sign)
        return lord.value if lord else None
    except Exception:
        return None
