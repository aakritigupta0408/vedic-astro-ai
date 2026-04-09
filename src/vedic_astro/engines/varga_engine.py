"""
varga_engine.py — Divisional chart (Varga) computation engine.

Pure deterministic math — zero LLM calls.
Implements the Parashari system for D1–D60 divisional charts.
D1, D9, and D10 are fully implemented; all others are registered via an
extensible framework that can be filled in incrementally.

Divisional formula school: PARASHARI (explicit declaration per architecture review)
    D3: Somanatha system (most widely used in modern Parashari software)
    D9: Standard Parashari navamsha (4 starting signs by element)
    D10: Standard Parashari dashamsha (odd/even sign rule)

Caching strategy:
    Cache key : sha256(chart_id + "d" + str(division))
    TTL       : permanent (derived from immutable natal data)
    Invalidate: cascade-delete on birth data correction (same prefix as natal)

Architecture corrections applied:
    - D60 precision check: raises InsufficientPrecisionError if birth time
      precision > 2 minutes (validated via time_precision_minutes in BirthData)
    - Formula school explicitly documented per division
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from vedic_astro.engines.natal_engine import (
    RASHI_NAMES,
    SIGN_LORDS,
    AyanamshaType,
    BhavaData,
    NatalChart,
    PlanetName,
    PlanetPosition,
    NakshatraData,
    Dignity,
    NAKSHATRA_SPAN,
    PADA_SPAN,
    RASHI_SPAN,
    compute_nakshatra,
    compute_dignity,
    RetrogradeDignityRule,
    longitude_to_sign,
)

# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class InsufficientPrecisionError(ValueError):
    """
    Raised when the birth time precision is insufficient for the requested
    divisional chart. D60 requires birth time accurate to ~2 minutes.
    """
    def __init__(self, division: int, required_minutes: int, given_minutes: int) -> None:
        super().__init__(
            f"D{division} requires birth time precision ≤ {required_minutes} minutes. "
            f"Given precision: {given_minutes} minutes. "
            "Rectify birth time before computing this divisional chart."
        )

# ─────────────────────────────────────────────────────────────────────────────
# Precision requirements per division
# ─────────────────────────────────────────────────────────────────────────────

# Maximum acceptable birth time error (minutes) for each division
PRECISION_REQUIREMENTS: dict[int, int] = {
    1:  60,   # D1 : any precision
    2:  30,   # D2 : within 30 minutes
    3:  20,
    4:  15,
    7:  10,
    9:  10,
    10: 10,
    12: 5,
    16: 5,
    20: 4,
    24: 3,
    27: 3,
    30: 2,
    40: 2,
    45: 2,
    60: 2,    # D60: within 2 minutes
}

# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DivisionalPosition:
    """
    A planet's position in a divisional chart.

    Longitude in the divisional chart is derived — it represents the midpoint
    of the division (not a precise ephemeris longitude). Used for sign, house,
    dignity, and nakshatra assignment only.
    """
    planet: PlanetName
    sign_number: int          # 1–12 in the divisional chart
    sign_name: str
    house: int                # 1–12 from divisional lagna
    degree_in_sign: float     # Approximate midpoint of the division (0–30)
    dignity: Dignity
    nakshatra: NakshatraData  # Nakshatra based on divisional longitude


@dataclass
class DivisionalChart:
    """
    A complete divisional (Varga) chart.

    Contains the lagna and planet placements in the divisional sign system.
    Shadbala is NOT re-computed for divisional charts — only natal D1 Shadbala
    is used (standard Parashari practice).
    """
    division: int
    parent_chart_id: str
    formula_school: str       # "parashari", "jaimini", etc.
    lagna_sign: int           # 1–12
    lagna_sign_name: str
    planets: dict[PlanetName, DivisionalPosition]
    bhavas: dict[int, BhavaData]


# ─────────────────────────────────────────────────────────────────────────────
# Division formula registry
# ─────────────────────────────────────────────────────────────────────────────

# Type for a divisional formula function:
# Input: (sign_number: int, degree_in_sign: float) → varga_sign_number (1–12)
VargaFormula = Callable[[int, float], int]

_FORMULA_REGISTRY: dict[int, tuple[VargaFormula, str]] = {}


def register_varga(division: int, school: str = "parashari") -> Callable:
    """
    Decorator to register a divisional chart formula.

    Usage:
        @register_varga(division=9, school="parashari")
        def d9_formula(sign: int, degree: float) -> int:
            ...
    """
    def decorator(fn: VargaFormula) -> VargaFormula:
        _FORMULA_REGISTRY[division] = (fn, school)
        return fn
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# Registered divisional formulas
# ─────────────────────────────────────────────────────────────────────────────

@register_varga(division=1, school="parashari")
def _d1_formula(sign: int, degree: float) -> int:
    """
    D1 (Rasi) — trivial. Sign is unchanged.
    Included for uniformity in the registry.
    """
    return sign


@register_varga(division=2, school="parashari")
def _d2_formula(sign: int, degree: float) -> int:
    """
    D2 (Hora) — Solar/Lunar division.
    First half (0°–15°): odd signs → Leo, even signs → Cancer.
    Second half (15°–30°): odd signs → Cancer, even signs → Leo.

    Interpretation: Sun's hora vs Moon's hora.
    Leo = Sun's hora; Cancer = Moon's hora.
    """
    is_odd = (sign % 2 == 1)
    first_half = degree < 15.0

    if is_odd:
        return 5 if first_half else 4   # Leo, Cancer
    else:
        return 4 if first_half else 5   # Cancer, Leo


@register_varga(division=3, school="somanatha")
def _d3_formula(sign: int, degree: float) -> int:
    """
    D3 (Drekkana) — Somanatha system (most common in modern Parashari software).
    Each sign divided into 3 parts of 10° each.

    Part 1 (0°–10°):  same sign
    Part 2 (10°–20°): 5th from same sign
    Part 3 (20°–30°): 9th from same sign

    Note: Parashari system uses (1st, 5th, 9th) from the sign itself.
    """
    part = int(degree / 10.0)           # 0, 1, or 2
    offsets = [0, 4, 8]                 # 1st, 5th, 9th (0-indexed)
    return ((sign - 1 + offsets[part]) % 12) + 1


@register_varga(division=4, school="parashari")
def _d4_formula(sign: int, degree: float) -> int:
    """
    D4 (Chaturthamsha) — each sign divided into 4 parts of 7°30' each.
    Movable signs: start from same sign.
    Fixed signs: start from 4th from same sign.
    Dual signs: start from 7th from same sign.
    Each subsequent part moves to the next sign.
    """
    part = int(degree / 7.5)            # 0, 1, 2, or 3
    # Sign modality: 1,4,7,10=movable; 2,5,8,11=fixed; 3,6,9,12=dual
    modality = (sign - 1) % 3          # 0=movable, 1=fixed, 2=dual
    start_offset = {0: 0, 1: 3, 2: 6}[modality]
    return ((sign - 1 + start_offset + part) % 12) + 1


@register_varga(division=7, school="parashari")
def _d7_formula(sign: int, degree: float) -> int:
    """
    D7 (Saptamsha) — each sign divided into 7 parts of 4°17' each.
    Odd signs: start from same sign, count forward.
    Even signs: start from 7th sign, count forward.
    """
    part = int(degree / (30.0 / 7))    # 0–6
    is_odd = (sign % 2 == 1)
    start = sign if is_odd else ((sign - 1 + 6) % 12) + 1
    return ((start - 1 + part) % 12) + 1


@register_varga(division=9, school="parashari")
def _d9_formula(sign: int, degree: float) -> int:
    """
    D9 (Navamsha) — each sign divided into 9 parts of 3°20' each.

    Starting sign by element:
        Fire (Aries=1, Leo=5, Sagittarius=9)    : start from Aries (sign 1)
        Earth (Taurus=2, Virgo=6, Capricorn=10) : start from Capricorn (sign 10)
        Air (Gemini=3, Libra=7, Aquarius=11)    : start from Libra (sign 7)
        Water (Cancer=4, Scorpio=8, Pisces=12)  : start from Cancer (sign 4)

    Each subsequent navamsha moves one sign forward.
    """
    navamsha_span = 30.0 / 9           # 3.333...°
    part = int(degree / navamsha_span) # 0–8

    # Starting sign (1-indexed) by element group
    element_starts: dict[str, int] = {
        "fire":  1,   # Aries
        "earth": 10,  # Capricorn
        "air":   7,   # Libra
        "water": 4,   # Cancer
    }
    sign_elements = {
        1: "fire", 2: "earth", 3: "air",  4: "water",
        5: "fire", 6: "earth", 7: "air",  8: "water",
        9: "fire", 10: "earth", 11: "air", 12: "water",
    }
    element = sign_elements[sign]
    start = element_starts[element]
    return ((start - 1 + part) % 12) + 1


@register_varga(division=10, school="parashari")
def _d10_formula(sign: int, degree: float) -> int:
    """
    D10 (Dashamsha) — each sign divided into 10 parts of 3° each.

    Odd signs (1,3,5,7,9,11): start from same sign, count forward.
    Even signs (2,4,6,8,10,12): start from 9th sign (sign + 8 in 0-indexed), count forward.
    """
    part = int(degree / 3.0)           # 0–9
    is_odd = (sign % 2 == 1)
    start_offset = 0 if is_odd else 8  # 9th sign = +8 (0-indexed)
    return ((sign - 1 + start_offset + part) % 12) + 1


@register_varga(division=12, school="parashari")
def _d12_formula(sign: int, degree: float) -> int:
    """
    D12 (Dvadashamsha) — each sign divided into 12 parts of 2°30' each.
    Starts from same sign, each part moves one sign forward.
    """
    part = int(degree / 2.5)
    return ((sign - 1 + part) % 12) + 1


@register_varga(division=16, school="parashari")
def _d16_formula(sign: int, degree: float) -> int:
    """
    D16 (Shodashamsha) — each sign divided into 16 parts of 1°52'30" each.
    Movable signs: start from Aries.
    Fixed signs: start from Leo.
    Dual signs: start from Sagittarius.
    """
    part = int(degree / (30.0 / 16))
    modality = (sign - 1) % 3
    starts = {0: 1, 1: 5, 2: 9}  # Aries, Leo, Sagittarius
    start = starts[modality]
    return ((start - 1 + part) % 12) + 1


@register_varga(division=20, school="parashari")
def _d20_formula(sign: int, degree: float) -> int:
    """
    D20 (Vimshamsha) — each sign divided into 20 parts of 1°30' each.
    Movable signs: start from Aries.
    Fixed signs: start from Sagittarius.
    Dual signs: start from Leo.
    """
    part = int(degree / 1.5)
    modality = (sign - 1) % 3
    starts = {0: 1, 1: 9, 2: 5}  # Aries, Sagittarius, Leo
    start = starts[modality]
    return ((start - 1 + part) % 12) + 1


@register_varga(division=24, school="parashari")
def _d24_formula(sign: int, degree: float) -> int:
    """
    D24 (Chaturvimshamsha / Siddhamsha) — each sign divided into 24 parts.
    Odd signs: start from Leo (sign 5).
    Even signs: start from Cancer (sign 4).
    """
    part = int(degree / (30.0 / 24))
    is_odd = (sign % 2 == 1)
    start = 5 if is_odd else 4  # Leo or Cancer
    return ((start - 1 + part) % 12) + 1


@register_varga(division=27, school="parashari")
def _d27_formula(sign: int, degree: float) -> int:
    """
    D27 (Bhamsha / Nakshatramsha) — each sign divided into 27 parts.
    Fire signs: start from Aries.
    Earth signs: start from Cancer.
    Air signs: start from Libra.
    Water signs: start from Capricorn.
    """
    part = int(degree / (30.0 / 27))
    sign_elements = {
        1: "fire", 2: "earth", 3: "air",  4: "water",
        5: "fire", 6: "earth", 7: "air",  8: "water",
        9: "fire", 10: "earth", 11: "air", 12: "water",
    }
    starts = {"fire": 1, "earth": 4, "air": 7, "water": 10}
    start = starts[sign_elements[sign]]
    return ((start - 1 + part) % 12) + 1


@register_varga(division=30, school="parashari")
def _d30_formula(sign: int, degree: float) -> int:
    """
    D30 (Trimshamsha) — irregular divisions within a sign.
    Parashari system (BPHS ch. 6):

    Odd signs (1,3,5,7,9,11):
        0°–5°   → Mars  → Aries/Scorpio   (ruled by Mars)
        5°–10°  → Saturn → Capricorn/Aquarius
        10°–18° → Jupiter → Sagittarius/Pisces
        18°–25° → Mercury → Gemini/Virgo
        25°–30° → Venus → Taurus/Libra

    Even signs (2,4,6,8,10,12): reverse — Venus first.
    Each segment maps to its ruling planet's own sign (primary sign for odd, secondary for even).
    """
    is_odd = (sign % 2 == 1)

    if is_odd:
        # Mars, Saturn, Jupiter, Mercury, Venus segments
        thresholds = [(5, 1), (10, 10), (18, 9), (25, 3), (30, 2)]
        # Target signs: Aries, Capricorn, Sagittarius, Gemini, Taurus
    else:
        # Venus, Mercury, Jupiter, Saturn, Mars segments (reversed)
        thresholds = [(5, 7), (12, 6), (20, 12), (25, 11), (30, 8)]
        # Target signs: Libra, Virgo, Pisces, Aquarius, Scorpio

    for threshold, target_sign in thresholds:
        if degree < threshold:
            return target_sign
    return thresholds[-1][1]


@register_varga(division=40, school="parashari")
def _d40_formula(sign: int, degree: float) -> int:
    """
    D40 (Khavedamsha) — each sign divided into 40 parts of 0°45' each.
    Movable signs: start from Aries.
    Fixed signs: start from Cancer.
    Dual signs: start from Libra.
    """
    part = int(degree / 0.75)
    modality = (sign - 1) % 3
    starts = {0: 1, 1: 4, 2: 7}
    start = starts[modality]
    return ((start - 1 + part) % 12) + 1


@register_varga(division=45, school="parashari")
def _d45_formula(sign: int, degree: float) -> int:
    """
    D45 (Akshavedamsha) — each sign divided into 45 parts of 0°40' each.
    Movable signs: start from Aries.
    Fixed signs: start from Leo.
    Dual signs: start from Sagittarius.
    """
    part = int(degree / (30.0 / 45))
    modality = (sign - 1) % 3
    starts = {0: 1, 1: 5, 2: 9}
    start = starts[modality]
    return ((start - 1 + part) % 12) + 1


@register_varga(division=5, school="parashari")
def _d5_formula(sign: int, degree: float) -> int:
    """
    D5 (Panchamsa) — 5 parts of 6° each.
    Odd signs: Aries(1), Aquarius(11), Sagittarius(9), Gemini(3), Libra(7).
    Even signs: Taurus(2), Virgo(6), Pisces(12), Capricorn(10), Scorpio(8).
    """
    part = int(degree / 6.0)
    odd_targets  = [1, 11, 9, 3, 7]
    even_targets = [2, 6, 12, 10, 8]
    targets = odd_targets if sign % 2 == 1 else even_targets
    return targets[part]


@register_varga(division=6, school="parashari")
def _d6_formula(sign: int, degree: float) -> int:
    """
    D6 (Shashthamsa) — 6 parts of 5° each.
    Odd signs: start from Aries (1).
    Even signs: start from Libra (7).
    """
    part = int(degree / 5.0)
    start = 1 if sign % 2 == 1 else 7
    return ((start - 1 + part) % 12) + 1


@register_varga(division=8, school="parashari")
def _d8_formula(sign: int, degree: float) -> int:
    """
    D8 (Ashtamsa) — 8 parts of 3°45' each.
    All signs start from Aries; each successive part advances one sign.
    """
    part = int(degree / (30.0 / 8))
    return ((0 + part) % 12) + 1   # Aries = index 0


@register_varga(division=11, school="parashari")
def _d11_formula(sign: int, degree: float) -> int:
    """
    D11 (Rudramsa / Labhamsa) — 11 parts of 2°43'38" each.
    Odd signs: start from Aries.
    Even signs: start from Libra.
    """
    part = int(degree / (30.0 / 11))
    start = 1 if sign % 2 == 1 else 7
    return ((start - 1 + part) % 12) + 1


def _generic_varga_formula(division: int, sign: int, degree: float) -> int:
    """
    Generic equal-division formula for D-numbers without a specific classical rule.

    Movable signs (1,4,7,10): start from same sign.
    Fixed signs (2,5,8,11):   start from 5th from same sign.
    Dual signs (3,6,9,12):    start from 9th from same sign.
    Each subsequent part advances one sign.
    """
    part = int(degree / (30.0 / division))
    modality = (sign - 1) % 3
    offsets = {0: 0, 1: 4, 2: 8}
    start = ((sign - 1 + offsets[modality]) % 12) + 1
    return ((start - 1 + part) % 12) + 1


# Register all remaining divisions (D13–D59 excluding already registered ones)
# using the generic equal-division formula so the registry is complete.
_ALREADY_REGISTERED = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 16, 20, 24, 27, 30, 40, 45, 60}
for _d in range(1, 61):
    if _d not in _ALREADY_REGISTERED:
        # Build a closure capturing _d to avoid late-binding
        def _make_generic(d: int):
            def _formula(sign: int, degree: float) -> int:
                return _generic_varga_formula(d, sign, degree)
            _formula.__name__ = f"_d{d}_formula"
            _formula.__doc__ = f"D{d} — generic equal-division formula (Parashari convention)."
            return _formula
        register_varga(_d, school="parashari_generic")(_make_generic(_d))


@register_varga(division=60, school="parashari")
def _d60_formula(sign: int, degree: float) -> int:
    """
    D60 (Shashtiamsha) — each sign divided into 60 parts of 0°30' each.
    Each part starts from the same sign and counts forward.
    Requires birth time precision ≤ 2 minutes.
    """
    part = int(degree / 0.5)           # 0–59
    return ((sign - 1 + part) % 12) + 1


# ─────────────────────────────────────────────────────────────────────────────
# Core computation
# ─────────────────────────────────────────────────────────────────────────────

def _compute_divisional_lagna(
    natal_lagna_longitude: float,
    division: int,
) -> int:
    """
    Compute the divisional chart lagna (ascendant sign).

    The lagna longitude is treated the same as any planet longitude.
    The divisional formula is applied to its sign and degree-in-sign.

    Args:
        natal_lagna_longitude: Sidereal lagna longitude (0–360°).
        division: The D-chart number.

    Returns:
        Divisional lagna sign (1–12).
    """
    formula, _ = _FORMULA_REGISTRY[division]
    sign = longitude_to_sign(natal_lagna_longitude)
    degree = natal_lagna_longitude % RASHI_SPAN
    return formula(sign, degree)


def _make_divisional_position(
    planet: PlanetName,
    natal_pos: PlanetPosition,
    division: int,
    divisional_lagna_sign: int,
    retrograde_rule: RetrogradeDignityRule = RetrogradeDignityRule.NONE,
) -> DivisionalPosition:
    """
    Compute a planet's position in a specific divisional chart.

    Args:
        planet:                 The graha being placed.
        natal_pos:              Planet's natal D1 position.
        division:               The D-chart number.
        divisional_lagna_sign:  Lagna sign in the divisional chart.
        retrograde_rule:        Retrograde dignity rule.

    Returns:
        DivisionalPosition for this planet in the divisional chart.
    """
    formula, _ = _FORMULA_REGISTRY[division]
    varga_sign = formula(natal_pos.sign_number, natal_pos.degree_in_sign)

    # House in divisional chart (whole-sign from divisional lagna)
    house = ((varga_sign - divisional_lagna_sign) % 12) + 1

    # Approximate longitude in divisional chart (midpoint of the division for nakshatra calc)
    part_span = RASHI_SPAN / division
    part_index = int(natal_pos.degree_in_sign / part_span)
    approx_deg_in_sign = (part_index + 0.5) * part_span
    approx_longitude = (varga_sign - 1) * RASHI_SPAN + approx_deg_in_sign

    nak_data = compute_nakshatra(approx_longitude)
    dignity = compute_dignity(planet, varga_sign, natal_pos.is_retrograde, retrograde_rule)

    return DivisionalPosition(
        planet=planet,
        sign_number=varga_sign,
        sign_name=RASHI_NAMES[varga_sign - 1],
        house=house,
        degree_in_sign=round(approx_deg_in_sign, 2),
        dignity=dignity,
        nakshatra=nak_data,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def compute_divisional_chart(
    natal_chart: NatalChart,
    division: int,
    time_precision_minutes: int = 60,
    retrograde_rule: RetrogradeDignityRule = RetrogradeDignityRule.NONE,
) -> DivisionalChart:
    """
    Compute a single divisional (Varga) chart from the natal D1 chart.

    Args:
        natal_chart:             The computed natal (D1) chart.
        division:                Which division to compute (1, 2, 3, ... 60).
        time_precision_minutes:  Birth time precision in minutes. Used to guard
                                 high-division charts that require better time accuracy.
        retrograde_rule:         Retrograde dignity adjustment rule.

    Returns:
        DivisionalChart with lagna, planet placements, and bhavas.

    Raises:
        ValueError:                 If division is not registered.
        InsufficientPrecisionError: If birth time precision is too low for the division.
    """
    if division not in _FORMULA_REGISTRY:
        registered = sorted(_FORMULA_REGISTRY.keys())
        raise ValueError(
            f"Division {division} is not implemented. "
            f"Registered divisions: {registered}"
        )

    # Precision guard
    required_precision = PRECISION_REQUIREMENTS.get(division, 2)
    if time_precision_minutes > required_precision:
        raise InsufficientPrecisionError(division, required_precision, time_precision_minutes)

    _, school = _FORMULA_REGISTRY[division]

    # Compute divisional lagna
    div_lagna_sign = _compute_divisional_lagna(natal_chart.lagna_longitude, division)
    div_lagna_name = RASHI_NAMES[div_lagna_sign - 1]

    # Compute divisional position for each planet
    div_planets: dict[PlanetName, DivisionalPosition] = {}
    for planet, natal_pos in natal_chart.planets.items():
        div_planets[planet] = _make_divisional_position(
            planet, natal_pos, division, div_lagna_sign, retrograde_rule
        )

    # Build bhavas for divisional chart
    planet_houses = {p: dp.house for p, dp in div_planets.items()}
    bhavas: dict[int, BhavaData] = {}
    for house_num in range(1, 13):
        sign_num = ((div_lagna_sign - 1 + house_num - 1) % 12) + 1
        sign_name = RASHI_NAMES[sign_num - 1]
        lord = SIGN_LORDS[sign_num]
        occupants = [p for p, h in planet_houses.items() if h == house_num]
        bhavas[house_num] = BhavaData(
            house_number=house_num,
            sign_number=sign_num,
            sign_name=sign_name,
            lord=lord,
            occupants=occupants,
        )

    return DivisionalChart(
        division=division,
        parent_chart_id=natal_chart.chart_id,
        formula_school=school,
        lagna_sign=div_lagna_sign,
        lagna_sign_name=div_lagna_name,
        planets=div_planets,
        bhavas=bhavas,
    )


def compute_required_charts(
    natal_chart: NatalChart,
    divisions: list[int],
    time_precision_minutes: int = 60,
    retrograde_rule: RetrogradeDignityRule = RetrogradeDignityRule.NONE,
    skip_on_precision_error: bool = True,
) -> dict[int, DivisionalChart]:
    """
    Compute multiple divisional charts for a natal chart.

    Only computes what is requested — never all 60 charts automatically.
    The caller (domain_mapper.py / orchestrator) determines which divisions
    are needed based on the query domain.

    Args:
        natal_chart:              Natal D1 chart.
        divisions:                List of division numbers to compute.
        time_precision_minutes:   Birth time precision for precision gating.
        retrograde_rule:          Retrograde dignity rule.
        skip_on_precision_error:  If True, skip divisions that fail precision check
                                  and log a warning instead of raising.

    Returns:
        Dict of division_number → DivisionalChart (only successfully computed).
    """
    import warnings
    result: dict[int, DivisionalChart] = {}

    for div in divisions:
        try:
            result[div] = compute_divisional_chart(
                natal_chart, div, time_precision_minutes, retrograde_rule
            )
        except InsufficientPrecisionError as e:
            if skip_on_precision_error:
                warnings.warn(f"Skipping D{div}: {e}", stacklevel=2)
            else:
                raise
        except ValueError as e:
            warnings.warn(f"Skipping D{div}: {e}", stacklevel=2)

    return result


def list_registered_divisions() -> list[tuple[int, str]]:
    """
    List all registered divisional chart formulas.

    Returns:
        List of (division_number, school_name) tuples, sorted by division.
    """
    return sorted(
        [(div, school) for div, (_, school) in _FORMULA_REGISTRY.items()],
        key=lambda x: x[0],
    )
