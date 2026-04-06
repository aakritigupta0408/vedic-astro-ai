"""
shadbala.py — Simplified Shadbala (Six-fold Planetary Strength) computation.

Shadbala is the classical Parashari system of measuring planetary strength
across six dimensions. Full Shadbala requires precise birth time and
extensive calculation; this module provides a simplified but useful
approximation suitable for weight calibration.

The six balas (strengths):
1. Sthana Bala  — Positional strength (sign dignity)
2. Dig Bala     — Directional strength (house placement)
3. Kala Bala    — Temporal strength (day/night, hora)
4. Chesta Bala  — Motional strength (speed, retrograde)
5. Naisargika Bala — Natural/inherent strength
6. Drik Bala    — Aspectual strength (benefic/malefic aspects received)

Each component returns a value 0.0–1.0. The composite Shadbala is the
weighted average of all six components.

Usage
-----
    from vedic_astro.learning.shadbala import compute_shadbala
    scores = compute_shadbala(chart, birth_datetime)
    # Returns dict: planet_name → ShadvalaScore
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Naisargika (natural) strength order — Sun strongest, Moon next, etc.
_NAISARGIKA_RANK: dict[str, float] = {
    "sun":     1.00,
    "moon":    0.86,
    "venus":   0.71,
    "jupiter": 0.57,
    "mercury": 0.43,
    "mars":    0.29,
    "saturn":  0.14,
}

# Dig Bala — directional strength by house
# Each planet has its strongest house (gets 1.0) and weakest (gets 0.0)
_DIG_BALA_STRONG: dict[str, int] = {
    "sun": 10, "mars": 10,       # strong in 10th (midheaven)
    "jupiter": 1, "mercury": 1,  # strong in 1st (ascendant)
    "moon": 4, "venus": 4,       # strong in 4th
    "saturn": 7,                  # strong in 7th
}
_DIG_BALA_WEAK: dict[str, int] = {
    "sun": 4, "mars": 4,
    "jupiter": 7, "mercury": 7,
    "moon": 10, "venus": 10,
    "saturn": 1,
}

# Dignity → Sthana Bala score
_DIGNITY_STHANA: dict[str, float] = {
    "exalted":      1.00,
    "moolatrikona": 0.83,
    "own":          0.75,
    "friend":       0.50,
    "neutral":      0.38,
    "enemy":        0.20,
    "debilitated":  0.00,
}

# Classical aspect strengths (from → to house offset)
# Planets casting full (1.0), 3/4 (0.75), 1/2 (0.5), 1/4 (0.25) aspects
_ASPECT_STRENGTHS: dict[str, dict[int, float]] = {
    # All planets have full 7th house aspect
    "full_7th": 1.0,
    # Mars has full aspects on 4th and 8th
    # Jupiter on 5th and 9th
    # Saturn on 3rd and 10th
}

# Benefic planets for Drik Bala
_NATURAL_BENEFICS = {"jupiter", "venus", "moon", "mercury"}
_NATURAL_MALEFICS = {"sun", "mars", "saturn", "rahu", "ketu"}


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ShadbalaScore:
    """Six-fold planetary strength for one planet."""
    planet: str

    sthana_bala:     float   # 0–1 positional/dignity strength
    dig_bala:        float   # 0–1 directional strength
    kala_bala:       float   # 0–1 temporal strength
    chesta_bala:     float   # 0–1 motional strength
    naisargika_bala: float   # 0–1 natural strength
    drik_bala:       float   # 0–1 aspectual strength

    composite:       float   # weighted composite 0–1
    virupas:         float   # traditional rupa units (composite × 60)

    label: str = ""          # "strong" | "moderate" | "weak"

    def __post_init__(self):
        if not self.label:
            if self.composite >= 0.65:
                self.label = "strong"
            elif self.composite >= 0.40:
                self.label = "moderate"
            else:
                self.label = "weak"

    def to_dict(self) -> dict:
        return {
            "planet": self.planet,
            "sthana":     round(self.sthana_bala, 3),
            "dig":        round(self.dig_bala, 3),
            "kala":       round(self.kala_bala, 3),
            "chesta":     round(self.chesta_bala, 3),
            "naisargika": round(self.naisargika_bala, 3),
            "drik":       round(self.drik_bala, 3),
            "composite":  round(self.composite, 3),
            "virupas":    round(self.virupas, 1),
            "label":      self.label,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_shadbala(
    chart: Any,
    birth_dt: Optional[datetime] = None,
) -> dict[str, ShadbalaScore]:
    """
    Compute simplified Shadbala for all planets in *chart*.

    Parameters
    ----------
    chart     : NatalChart object from natal_engine.
    birth_dt  : Birth datetime (used for Kala Bala). If None, uses noon.

    Returns
    -------
    dict mapping planet name (str) → ShadbalaScore
    """
    results: dict[str, ShadbalaScore] = {}

    planets_data = chart.planets  # dict: PlanetName → PlanetPosition

    # Build a position lookup by house for aspect calculations
    house_occupants: dict[int, list[str]] = {}
    for p, pos in planets_data.items():
        h = pos.house
        house_occupants.setdefault(h, []).append(p.value.lower())

    for planet_enum, position in planets_data.items():
        pname = planet_enum.value.lower()

        sthana  = _calc_sthana_bala(pname, position)
        dig     = _calc_dig_bala(pname, position)
        kala    = _calc_kala_bala(pname, birth_dt)
        chesta  = _calc_chesta_bala(pname, position)
        naisar  = _NAISARGIKA_RANK.get(pname, 0.30)
        drik    = _calc_drik_bala(pname, position, planets_data)

        # Weights: Sthana and Chesta are most important classically
        weights = [0.25, 0.15, 0.15, 0.20, 0.10, 0.15]
        values  = [sthana, dig, kala, chesta, naisar, drik]
        composite = sum(w * v for w, v in zip(weights, values))

        results[pname] = ShadbalaScore(
            planet=pname,
            sthana_bala=round(sthana, 3),
            dig_bala=round(dig, 3),
            kala_bala=round(kala, 3),
            chesta_bala=round(chesta, 3),
            naisargika_bala=round(naisar, 3),
            drik_bala=round(drik, 3),
            composite=round(composite, 3),
            virupas=round(composite * 60, 1),
        )

    return results


def _calc_sthana_bala(planet: str, pos: Any) -> float:
    """Dignity-based positional strength."""
    dignity = getattr(pos, "dignity", None)
    if dignity is None:
        return 0.40
    dval = dignity.value.lower() if hasattr(dignity, "value") else str(dignity).lower()
    # Map common dignity strings
    for key, score in _DIGNITY_STHANA.items():
        if key in dval:
            return score
    return 0.38


def _calc_dig_bala(planet: str, pos: Any) -> float:
    """Directional strength based on house placement."""
    house = getattr(pos, "house", 1) or 1
    strong_house = _DIG_BALA_STRONG.get(planet, 1)
    weak_house   = _DIG_BALA_WEAK.get(planet, 7)

    # Distance from strongest house (circular, 12 houses)
    dist_to_strong = min(abs(house - strong_house), 12 - abs(house - strong_house))
    dist_to_weak   = min(abs(house - weak_house),   12 - abs(house - weak_house))

    # Normalise: at strong_house → 1.0, at weak_house → 0.0
    if dist_to_strong == 0:
        return 1.0
    if dist_to_weak == 0:
        return 0.0

    total = dist_to_strong + dist_to_weak
    return round(dist_to_weak / total, 3) if total > 0 else 0.5


def _calc_kala_bala(planet: str, birth_dt: Optional[datetime]) -> float:
    """
    Temporal strength — simplified:
    - Sun/Jupiter/Venus stronger by day
    - Moon/Mars/Saturn stronger by night
    - Mercury neutral
    """
    if birth_dt is None:
        return 0.50

    hour = birth_dt.hour + birth_dt.minute / 60.0
    is_day = 6.0 <= hour < 18.0

    day_planets  = {"sun", "jupiter", "venus"}
    night_planets = {"moon", "mars", "saturn"}

    if planet in day_planets:
        return 0.80 if is_day else 0.35
    if planet in night_planets:
        return 0.80 if not is_day else 0.35
    return 0.55  # mercury / nodes


def _calc_chesta_bala(planet: str, pos: Any) -> float:
    """
    Motional strength:
    - Retrograde planets have heightened Chesta Bala (paradoxically stronger)
    - Combusted planets lose Chesta Bala significantly
    - Direct planets: moderate strength
    """
    is_retro  = getattr(pos, "is_retrograde", False)
    is_combust = getattr(pos, "is_combust", False)

    # Nodes don't have Chesta Bala
    if planet in ("rahu", "ketu"):
        return 0.40

    if is_combust:
        return 0.15  # combust = very weak chesta
    if is_retro:
        return 0.85  # retrograde = strong chesta (bhrashtanga + vakri)
    return 0.55  # direct motion = average


def _calc_drik_bala(planet: str, pos: Any, all_planets: Any) -> float:
    """
    Aspectual strength — net effect of aspects received.

    Benefic aspects add strength; malefic aspects subtract.
    Uses simplified whole-sign aspect rules.
    """
    planet_house = getattr(pos, "house", 1) or 1
    score = 0.50  # neutral baseline

    for other_enum, other_pos in all_planets.items():
        other_name  = other_enum.value.lower()
        if other_name == planet:
            continue

        other_house = getattr(other_pos, "house", 1) or 1
        offset = ((planet_house - other_house) % 12) + 1  # 1–12

        # Check if other planet aspects this planet
        aspect_str = _get_aspect_strength(other_name, offset)
        if aspect_str == 0:
            continue

        if other_name in _NATURAL_BENEFICS:
            score += 0.12 * aspect_str
        elif other_name in _NATURAL_MALEFICS:
            score -= 0.08 * aspect_str

    return max(0.0, min(1.0, score))


def _get_aspect_strength(planet: str, house_offset: int) -> float:
    """
    Return aspect strength (0–1) cast by *planet* to a planet
    *house_offset* houses ahead (1 = conjunction, 7 = full opposition).
    """
    # All planets aspect 7th house (full)
    if house_offset == 7:
        return 1.0
    # Conjunction treated separately (same house = 1)
    if house_offset == 1:
        return 1.0

    special: dict[str, dict[int, float]] = {
        "mars":    {4: 1.0, 8: 1.0},
        "jupiter": {5: 1.0, 9: 1.0},
        "saturn":  {3: 1.0, 10: 1.0},
        "rahu":    {5: 0.5, 9: 0.5},
        "ketu":    {5: 0.5, 9: 0.5},
    }

    planet_aspects = special.get(planet, {})
    return planet_aspects.get(house_offset, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Summary helper
# ─────────────────────────────────────────────────────────────────────────────

def shadbala_summary(scores: dict[str, ShadbalaScore]) -> str:
    """Return a markdown table summary of Shadbala scores."""
    lines = [
        "| Planet | Sthana | Dig | Kala | Chesta | Naisar | Drik | **Total** | Strength |",
        "|--------|--------|-----|------|--------|--------|------|-----------|----------|",
    ]
    for pname, s in scores.items():
        lines.append(
            f"| {pname.title()} "
            f"| {s.sthana_bala:.2f} "
            f"| {s.dig_bala:.2f} "
            f"| {s.kala_bala:.2f} "
            f"| {s.chesta_bala:.2f} "
            f"| {s.naisargika_bala:.2f} "
            f"| {s.drik_bala:.2f} "
            f"| **{s.composite:.2f}** "
            f"| {s.label} |"
        )
    return "\n".join(lines)
