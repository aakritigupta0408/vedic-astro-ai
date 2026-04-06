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
    Can be constructed from a CalibrationResult.weights dict.
    """
    natal_weight:   float = 0.35
    dasha_weight:   float = 0.30
    transit_weight: float = 0.25
    yoga_weight:    float = 0.10
    dosha_weight:   float = 0.10

    # Sade Sati severity multiplier applied to transit score (additive penalty)
    sadesati_penalty: float = 0.15

    # Retrograde dasha lord penalty
    retrograde_penalty: float = 0.10

    # Combust planet penalty (applied to natal score)
    combust_penalty: float = 0.08

    @classmethod
    def from_calibration(cls, cal_weights: dict) -> "ScoringWeights":
        """Create ScoringWeights from a CalibrationResult.weights dict."""
        return cls(
            natal_weight=cal_weights.get("natal",   0.35),
            dasha_weight=cal_weights.get("dasha",   0.30),
            transit_weight=cal_weights.get("transit", 0.25),
            yoga_weight=cal_weights.get("yoga",     0.10),
            dosha_weight=cal_weights.get("dosha",   0.10),
        )


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
    ``navamsha_strength`` is the D9 sub-score used within natal_strength.
    """
    domain: str
    natal_strength:    float
    dasha_activation:  float
    transit_trigger:   float
    yoga_support:      float
    dosha_penalty:     float
    final_score:       float
    interpretation:    str
    navamsha_strength: float = 0.0   # D9 sub-score (70% D1 + 30% D9 → natal_strength)
    d1_strength:       float = 0.0   # pure D1 sub-score before D9 blend
    weights_used:      dict = field(default_factory=dict)  # actual weights used
    notes: list[str] = field(default_factory=list)

    @property
    def formula(self) -> str:
        """
        Human-readable weighted formula string.

        Example:
            (0.35×0.62 + 0.30×0.71 + 0.25×0.55 + 0.10×0.80) − 0.20×0.30 = 0.634
        """
        w = self.weights_used or {
            "natal": 0.35, "dasha": 0.30, "transit": 0.25, "yoga": 0.10
        }
        wn  = w.get("natal",   0.35)
        wd  = w.get("dasha",   0.30)
        wt  = w.get("transit", 0.25)
        wy  = w.get("yoga",    0.10)
        dp  = self.dosha_penalty
        return (
            f"({wn:.2f}×{self.natal_strength:.2f}"
            f" + {wd:.2f}×{self.dasha_activation:.2f}"
            f" + {wt:.2f}×{self.transit_trigger:.2f}"
            f" + {wy:.2f}×{self.yoga_support:.2f})"
            f" − 0.20×{dp:.2f}"
            f" = **{self.final_score:.3f}**"
        )

    @property
    def score_table_md(self) -> str:
        """
        Markdown table showing each component weight, score, and contribution.
        Suitable for embedding directly in the chat response.
        """
        w = self.weights_used or {
            "natal": 0.35, "dasha": 0.30, "transit": 0.25, "yoga": 0.10
        }
        wn  = w.get("natal",   0.35)
        wd  = w.get("dasha",   0.30)
        wt  = w.get("transit", 0.25)
        wy  = w.get("yoga",    0.10)

        rows = [
            ("Natal Foundation (D1+D9)", f"{wn*100:.0f}%", self.natal_strength,
             wn * self.natal_strength, "+"),
            ("Vimshottari Dasha",        f"{wd*100:.0f}%", self.dasha_activation,
             wd * self.dasha_activation, "+"),
            ("Gochara Transits",         f"{wt*100:.0f}%", self.transit_trigger,
             wt * self.transit_trigger, "+"),
            ("Yoga / Dosha Support",     f"{wy*100:.0f}%", self.yoga_support,
             wy * self.yoga_support, "+"),
            ("Dosha Penalty",            "—",              self.dosha_penalty,
             -0.20 * self.dosha_penalty, "−"),
        ]

        lines = [
            "| Layer | Weight | Score | Contribution |",
            "|-------|--------|-------|-------------|",
        ]
        for label, weight, score, contrib, sign in rows:
            bar_filled = int(round(score * 10))
            bar = "█" * bar_filled + "░" * (10 - bar_filled)
            contrib_str = f"{contrib:+.3f}"
            lines.append(
                f"| {label} | {weight} | {score:.2f} `{bar}` | {contrib_str} |"
            )
        lines.append(
            f"| **COMPOSITE** | | **{self.final_score:.3f}** | "
            f"**{self.interpretation.replace('_', ' ').title()}** |"
        )

        # D9 sub-breakdown if available
        d9_note = ""
        if self.d1_strength and self.navamsha_strength:
            d9_note = (
                f"\n> Natal = 70% × D1({self.d1_strength:.2f}) "
                f"+ 30% × D9-Navamsha({self.navamsha_strength:.2f})"
                f" = {self.natal_strength:.2f}"
            )

        return "\n".join(lines) + d9_note

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


def _d9_dignity_for_sign(planet: str, sign: int) -> str:
    """
    Compute Parashari dignity for *planet* (PlanetName.value string) in *sign* (1–12).
    Delegates to feature_builder to keep the implementation in one place.
    """
    from vedic_astro.learning.feature_builder import _d9_dignity_for_sign as _impl
    return _impl(planet, sign)


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
            Includes component scores, D9 navamsha sub-score, formula string,
            and a ready-to-embed Markdown score table.
        """
        domain = domain.lower()
        notes: list[str] = []

        d1_raw, d9_raw, natal = self._score_natal_strength(features, domain, notes)
        dasha   = self._score_dasha_activation(features, domain, notes)
        transit = self._score_transit_trigger(features, notes)
        yoga    = self._score_yoga_support(features, domain, notes)
        dosha   = self._score_dosha_penalty(features, domain, notes)

        w = self._w
        # Normalise positive weights so they sum to 1
        pos_total = w.natal_weight + w.dasha_weight + w.transit_weight + w.yoga_weight
        wn = w.natal_weight   / pos_total if pos_total else 0.35
        wd = w.dasha_weight   / pos_total if pos_total else 0.30
        wt = w.transit_weight / pos_total if pos_total else 0.25
        wy = w.yoga_weight    / pos_total if pos_total else 0.10

        numerator = wn * natal + wd * dasha + wt * transit + wy * yoga
        # Subtract dosha penalty as a fixed 20% deduction on the penalty value
        final = max(0.0, min(1.0, numerator - dosha * 0.20))

        weights_used = {"natal": round(wn, 4), "dasha": round(wd, 4),
                        "transit": round(wt, 4), "yoga": round(wy, 4)}

        return ScoreBreakdown(
            domain=domain,
            natal_strength=round(natal, 3),
            dasha_activation=round(dasha, 3),
            transit_trigger=round(transit, 3),
            yoga_support=round(yoga, 3),
            dosha_penalty=round(dosha, 3),
            final_score=round(final, 3),
            interpretation=_interpret(final),
            navamsha_strength=round(d9_raw, 3) if d9_raw is not None else 0.0,
            d1_strength=round(d1_raw, 3),
            weights_used=weights_used,
            notes=notes,
        )

    # ── Component scorers ─────────────────────────────────────────────────

    def _score_natal_strength(
        self,
        f: AstroFeatures,
        domain: str,
        notes: list[str],
    ) -> tuple[float, Optional[float], float]:
        """
        Assess natal planet dignity and house placement for the domain.

        Returns (d1_score, d9_score_or_None, blended_natal_score).

        D1 and D9 are blended: natal = 0.70 × D1 + 0.30 × D9 (when D9 available).

        D1 scoring steps:
        1. Identify key planets and houses for the domain.
        2. Score each key planet: dignity score × house bonus × combust penalty.
        3. Penalise lagna lord if in dusthana.
        4. Average across key planets.

        D9 scoring: compute dignity of the same key planets in D9 sign,
        apply the same dignity-score lookup, then average.
        """
        key_planets = _DOMAIN_KEY_PLANETS.get(domain) or list(f.planet_signs.keys())
        key_houses  = set(_DOMAIN_KEY_HOUSES.get(domain, [1, 4, 7, 10]))

        # ── D1 scoring ────────────────────────────────────────────────────
        d1_scores = []
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
            d1_scores.append(p_score)

            if dignity == "debilitated":
                notes.append(f"{planet.title()} debilitated — weakens {domain} prospects")
            elif dignity == "exalted" and house in key_houses:
                notes.append(f"{planet.title()} exalted in house {house} — strong {domain} indicator")

        d1_raw = sum(d1_scores) / len(d1_scores) if d1_scores else 0.5

        # Lagna lord penalty on D1 score
        lagna_lord = _get_lagna_lord(f.lagna_sign)
        if lagna_lord:
            ll_house = f.planet_houses.get(lagna_lord, 0)
            if ll_house in _DUSTHANA_HOUSES:
                notes.append(f"Lagna lord in {ll_house}th (dusthana) — overall constitution weakened")
                d1_raw = max(0.0, d1_raw - 0.08)

        # ── D9 (Navamsha) scoring ─────────────────────────────────────────
        d9_raw: Optional[float] = None
        if f.d9_planet_signs:
            d9_scores = []
            for planet in key_planets:
                d9_sign = f.d9_planet_signs.get(planet)
                if d9_sign:
                    dig = _d9_dignity_for_sign(planet, d9_sign)
                    d9_scores.append(DIGNITY_SCORES.get(dig, 0.40))
            if d9_scores:
                d9_raw = sum(d9_scores) / len(d9_scores)
                # Vargottama bonus: planet in same sign in D1 and D9
                vargottama = [
                    p for p in key_planets
                    if f.planet_signs.get(p) and f.planet_signs.get(p) == f.d9_planet_signs.get(p)
                ]
                if vargottama:
                    d9_raw = min(1.0, d9_raw + 0.05 * len(vargottama))
                    notes.append(
                        f"Vargottama planet(s): {', '.join(p.title() for p in vargottama[:3])} "
                        f"(same sign in D1 & D9 — confirmed strength)"
                    )

        # ── Blend D1 + D9 ─────────────────────────────────────────────────
        if d9_raw is not None:
            blended = 0.70 * d1_raw + 0.30 * d9_raw
            notes.append(
                f"Natal: D1={d1_raw:.2f}×70% + D9-Navamsha={d9_raw:.2f}×30% = {blended:.2f}"
            )
        else:
            blended = d1_raw

        return d1_raw, d9_raw, blended

    def _score_dasha_activation(
        self,
        f: AstroFeatures,
        domain: str,
        notes: list[str],
    ) -> float:
        """
        Assess whether the active dasha amplifies the domain.

        Checks (in order of importance):
        1. Maha lord D1 dignity + house placement.
        2. D9 varga depth of maha lord (how fully promise manifests).
        3. D10 dignity bonus for career queries.
        4. Whether dasha lord IS a yoga-forming planet (yoga fructification).
        5. Maha/Antar lord mutual friendship.
        6. Whether dasha lords rule domain-key houses.
        7. Timing fraction.
        8. Retrograde penalty.
        """
        if not f.maha_lord:
            return 0.5   # no dasha data

        maha_dignity = f.maha_lord_dignity
        antar_dignity = f.antar_lord_dignity

        maha_score  = DIGNITY_SCORES.get(maha_dignity, 0.40)
        antar_score = DIGNITY_SCORES.get(antar_dignity, 0.40) if f.antar_lord else 0.5

        # Maha lord house placement (D1)
        maha_house = f.maha_lord_house
        if maha_house in _KENDRA_HOUSES | _TRIKONA_HOUSES:
            maha_score = min(1.0, maha_score + 0.12)
        elif maha_house in _DUSTHANA_HOUSES:
            maha_score = max(0.0, maha_score - 0.12)

        # ── NEW: D9 varga depth modifier ─────────────────────────────────
        # The dasha lord's D9 dignity determines how fully it delivers its D1
        # promise.  Exalted in D9 → amplified; debilitated → curtailed.
        d9_dig = getattr(f, "maha_lord_d9_dignity", "neutral")
        d9_dignity_score = DIGNITY_SCORES.get(d9_dig, 0.40)
        # Normalise: neutral (0.40) → 1.0, exalted (1.0) → 1.50, debil (0.0) → 0.50
        d9_varga_mult = 0.50 + d9_dignity_score
        d9_varga_mult = max(0.60, min(1.40, d9_varga_mult))
        maha_score = min(1.0, maha_score * d9_varga_mult)
        if d9_dig in ("exalted", "moolatrikona", "own"):
            notes.append(
                f"Dasha lord {f.maha_lord} is {d9_dig} in D9 — promise amplified"
            )
        elif d9_dig == "debilitated":
            notes.append(
                f"Dasha lord {f.maha_lord} is debilitated in D9 — D1 promise curtailed"
            )

        # ── NEW: D10 bonus for career domain ─────────────────────────────
        if domain == "career":
            d10_dig = getattr(f, "maha_lord_d10_dignity", "neutral")
            if d10_dig in ("exalted", "moolatrikona", "own"):
                maha_score = min(1.0, maha_score + 0.08)
                notes.append(
                    f"Dasha lord {f.maha_lord} is {d10_dig} in D10 — career delivery confirmed"
                )

        # ── NEW: Yoga fructification by dasha ────────────────────────────
        # If the maha lord IS one of the yoga-forming planets, the yoga is
        # being directly activated by the dasha — strong bonus.
        activated_yogas = getattr(f, "dasha_activates_yogas", [])
        yoga_fruct_bonus = 0.0
        if activated_yogas:
            yoga_fruct_bonus = min(0.15, 0.08 * len(activated_yogas))
            notes.append(
                f"Dasha lord activates yoga(s): {', '.join(activated_yogas[:3])} "
                f"— yoga fructifying now"
            )
        antar_activated = getattr(f, "antar_activates_yogas", [])
        if antar_activated:
            yoga_fruct_bonus = min(0.15, yoga_fruct_bonus + 0.04 * len(antar_activated))

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

        # Timing: dasha early vs late
        timing_mult = 1.0
        if f.maha_elapsed_fraction < 0.2:
            timing_mult = 1.05
        elif f.maha_elapsed_fraction > 0.85:
            timing_mult = 0.95

        score = (0.60 * maha_score + 0.40 * antar_score) * friendship_mult * timing_mult
        score = min(1.0, score + domain_bonus + yoga_fruct_bonus - retro_pen)
        return max(0.0, score)

    def _score_transit_trigger(
        self,
        f: AstroFeatures,
        notes: list[str],
    ) -> float:
        """
        Compute weighted gochara (transit) trigger score.

        Weights outer planets more heavily (Saturn/Jupiter/Rahu/Ketu).

        NEW interdependence checks:
        1. Dasha-transit confluence: transiting planet conjunct natal dasha lord
           (the same planetary energy running in both timing systems → amplified).
        2. Transit-yoga activation: transit over a yoga-forming planet's natal
           position "switches on" the yoga for immediate fructification.
        3. Applies Sade Sati penalty when active.
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

        # ── NEW: Dasha-transit confluence ─────────────────────────────────
        # Transit planet conjunct natal dasha lord = double activation
        if getattr(f, "transit_conjunct_dasha_lord", False):
            conj_p = getattr(f, "transit_conjunct_dasha_lord_planet", "transit planet")
            base = min(1.0, base + 0.12)
            notes.append(
                f"Dasha-transit confluence: {conj_p} transiting over natal "
                f"dasha lord {f.maha_lord} — double activation of timing"
            )

        # ── NEW: Transit-yoga activation ──────────────────────────────────
        # Transit over yoga-forming planet's natal position activates the yoga
        activated_yogas = getattr(f, "transit_activates_yogas", [])
        if activated_yogas:
            transit_yoga_bonus = min(0.10, 0.05 * len(activated_yogas))
            base = min(1.0, base + transit_yoga_bonus)
            notes.append(
                f"Transit activating yoga(s): {', '.join(activated_yogas[:3])} "
                f"— timing window for yoga results"
            )

        return base

    def _score_yoga_support(
        self,
        f: AstroFeatures,
        domain: str,
        notes: list[str],
    ) -> float:
        """
        Score active yogas accounting for their ACTUAL ACTIVATION STATE.

        A natal yoga that is not being activated by the current dasha or
        transit is dormant and should contribute less to the score.

        Activation tiers:
        - Dasha + transit both activate the yoga → 1.25× strength (double trigger)
        - Dasha alone activates → 1.0× (fully fructifying)
        - Transit alone activates → 0.85× (partially triggered)
        - Neither activates → 0.55× (natally present but dormant)

        Doshas are scored separately (see _score_dosha_penalty).
        """
        if not f.active_yoga_names:
            return 0.40  # neutral when no data

        relevant = _YOGA_DOMAIN_RELEVANCE.get(domain, set())

        relevant_names = []
        if relevant:
            relevant_names = [
                y for y in f.active_yoga_names
                if any(r.lower() in y.lower() for r in relevant)
            ]
            all_names = relevant_names or f.active_yoga_names
        else:
            all_names = f.active_yoga_names

        if not all_names:
            return 0.40

        dasha_acts   = set(getattr(f, "dasha_activates_yogas", []))
        transit_acts = set(getattr(f, "transit_activates_yogas", []))

        effective_strengths = []
        fully_active = []
        dormant = []

        for yoga_name in all_names:
            base_strength = f.yoga_strengths.get(yoga_name, 0.5)
            d_active = yoga_name in dasha_acts
            t_active = yoga_name in transit_acts

            if d_active and t_active:
                mult = 1.25    # double trigger — yoga is at peak expression
                fully_active.append(yoga_name)
            elif d_active:
                mult = 1.00    # dasha alone — normal fructification
                fully_active.append(yoga_name)
            elif t_active:
                mult = 0.85    # transit alone — partially triggered
            else:
                mult = 0.55    # dormant — natal promise only, not yet operative
                dormant.append(yoga_name)

            effective_strengths.append(min(1.0, base_strength * mult))

        avg = sum(effective_strengths) / len(effective_strengths)
        count_bonus = min(0.10, len(effective_strengths) * 0.03)
        score = min(1.0, avg + count_bonus)

        if fully_active:
            notes.append(
                f"Active (dasha-fructifying) yoga(s): {', '.join(fully_active[:3])}"
            )
        if dormant:
            notes.append(
                f"Dormant yoga(s) — natal promise, not yet triggered by dasha/transit: "
                f"{', '.join(dormant[:3])}"
            )
        if relevant_names:
            notes.append(
                f"{len(relevant_names)} domain-relevant yoga(s) for {domain}"
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
