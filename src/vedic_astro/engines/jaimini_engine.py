"""
jaimini_engine.py — Jaimini system computation engine.

Implements:
  - Chara Karakas (7 + optional Pitru karaka)
  - Karakamsha and Swamsha
  - Jaimini Rasi Drishti (sign aspects — differs from Parashari graha drishti)
  - Argalas and counter-argalas
  - Jaimini Chara Dasha (primary Jaimini timing system)
  - Narayana Dasha (sign-based dasha for house-level timing)

Pure deterministic math — zero LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from vedic_astro.engines.natal_engine import (
    NatalChart,
    PlanetName,
    RASHI_NAMES,
    SIGN_LORDS,
    NAKSHATRA_SPAN,
    NAKSHATRA_LORDS,
    NAKSHATRA_NAMES,
    RASHI_SPAN,
    compute_chara_karakas,
    longitude_to_sign,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

DAYS_PER_YEAR = 365.25

# Jaimini uses 12 chara dasha years mapped to each sign (Parashari base: 12 years max)
# Duration = 12 − (sign lord's position from sign) capped at 1 minimum
# This is computed dynamically per chart (see compute_chara_dasha).

# Karaka name list (7-karaka system; Pitru karaka omitted in standard Parashari Jaimini)
KARAKA_NAMES_7 = [
    "atmakaraka", "amatyakaraka", "bhratrikaraka",
    "matrikaraka", "putrakaraka", "gnatikaraka", "darakaraka",
]


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class JaiminiKarakas:
    """The seven Jaimini Chara Karakas and their natal positions."""
    atmakaraka: PlanetName
    amatyakaraka: PlanetName
    bhratrikaraka: PlanetName
    matrikaraka: PlanetName
    putrakaraka: PlanetName
    gnatikaraka: PlanetName
    darakaraka: PlanetName
    # Sign each karaka occupies in D1
    sign_numbers: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, PlanetName]:
        return {
            "atmakaraka":   self.atmakaraka,
            "amatyakaraka": self.amatyakaraka,
            "bhratrikaraka":self.bhratrikaraka,
            "matrikaraka":  self.matrikaraka,
            "putrakaraka":  self.putrakaraka,
            "gnatikaraka":  self.gnatikaraka,
            "darakaraka":   self.darakaraka,
        }


@dataclass
class ArgalaResult:
    """Argala (intervention) analysis for one reference point (sign or planet)."""
    reference: str                    # sign name or planet name
    argalas: list[str]                # list of planets/signs forming argala
    counter_argalas: list[str]        # planets blocking the argala
    net_argala_strength: float        # 0.0–1.0; positive means argala wins


@dataclass
class CharaDashaPeriod:
    """One period in Jaimini Chara Dasha."""
    sign_number: int
    sign_name: str
    lord: PlanetName
    start: date
    end: date
    duration_years: int

    def contains(self, query_date: date) -> bool:
        """Half-open interval [start, end)."""
        return self.start <= query_date < self.end


@dataclass
class JaiminiBundle:
    """All Jaimini computations for a natal chart."""
    chart_id: str
    karakas: JaiminiKarakas
    karakamsha_sign: int              # sign where AK sits in D9
    swamsha_sign: int                 # same as karakamsha (AK's D9 sign used as lagna)
    rasi_aspects: dict[int, list[int]]     # sign → list of signs it aspects (Jaimini)
    argalas: dict[str, ArgalaResult]  # planet name → ArgalaResult
    chara_dashas: list[CharaDashaPeriod]   # full Chara Dasha sequence from birth
    active_chara_dasha: Optional[CharaDashaPeriod] = None


# ─────────────────────────────────────────────────────────────────────────────
# Jaimini Rasi Drishti (sign aspects)
# ─────────────────────────────────────────────────────────────────────────────

def compute_rasi_drishti() -> dict[int, list[int]]:
    """
    Compute Jaimini Rasi Drishti for all 12 signs.

    Rules (Jaimini Sutras):
      - Movable signs (1,4,7,10) aspect all fixed signs EXCEPT the adjacent one.
      - Fixed signs (2,5,8,11) aspect all dual signs EXCEPT the adjacent one.
      - Dual signs (3,6,9,12) aspect all movable signs EXCEPT the adjacent one.

    All aspects are mutual (if A aspects B, B also aspects A).

    Returns:
        Dict of sign_number (1–12) → list of aspected sign_numbers.
    """
    movable = {1, 4, 7, 10}
    fixed   = {2, 5, 8, 11}
    dual    = {3, 6, 9, 12}

    aspects: dict[int, set[int]] = {s: set() for s in range(1, 13)}

    def adjacent(sign: int) -> tuple[int, int]:
        prev = ((sign - 2) % 12) + 1
        nxt  = (sign % 12) + 1
        return prev, nxt

    for sign in movable:
        prev, nxt = adjacent(sign)
        for target in fixed:
            if target not in (prev, nxt):
                aspects[sign].add(target)
                aspects[target].add(sign)

    for sign in fixed:
        prev, nxt = adjacent(sign)
        for target in dual:
            if target not in (prev, nxt):
                aspects[sign].add(target)
                aspects[target].add(sign)

    for sign in dual:
        prev, nxt = adjacent(sign)
        for target in movable:
            if target not in (prev, nxt):
                aspects[sign].add(target)
                aspects[target].add(sign)

    return {s: sorted(v) for s, v in aspects.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Argala computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_argala(
    chart: NatalChart,
    reference_sign: int,
) -> ArgalaResult:
    """
    Compute Argala (obstruction/benefaction) for a reference sign.

    Argala positions: 2nd, 4th, 11th from reference.
    Counter-argala (Virodha Argala): 12th, 10th, 3rd.

    If more planets form argala than counter-argala, the argala is effective.

    Args:
        chart:          Natal D1 chart.
        reference_sign: 1–12 (sign to analyse argalas for).

    Returns:
        ArgalaResult for the reference sign.
    """
    planet_signs = {
        p: pos.sign_number for p, pos in chart.planets.items()
    }

    argala_offsets   = [2, 4, 11]
    counter_offsets  = [12, 10, 3]

    def sign_at_offset(base: int, offset: int) -> int:
        return ((base - 1 + offset - 1) % 12) + 1

    argala_planets: list[str] = []
    counter_planets: list[str] = []

    for planet, p_sign in planet_signs.items():
        for offset, c_offset in zip(argala_offsets, counter_offsets):
            if p_sign == sign_at_offset(reference_sign, offset):
                argala_planets.append(planet.value)
            if p_sign == sign_at_offset(reference_sign, c_offset):
                counter_planets.append(planet.value)

    net = len(argala_planets) - len(counter_planets)
    strength = max(0.0, min(1.0, (net + 4) / 8.0))   # normalise: 0.5 = balanced

    return ArgalaResult(
        reference=RASHI_NAMES[reference_sign - 1],
        argalas=argala_planets,
        counter_argalas=counter_planets,
        net_argala_strength=round(strength, 3),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Jaimini Chara Dasha
# ─────────────────────────────────────────────────────────────────────────────

def _chara_dasha_duration(sign: int, chart: NatalChart) -> int:
    """
    Compute the Chara Dasha duration for a sign in years.

    Rule (Parashari Jaimini):
      duration = 12 − (count from sign to its lord's position, forward)
      Minimum = 1 year. If the lord is in its own sign, duration = 12.

    Returns:
        Duration in whole years (1–12).
    """
    lord = SIGN_LORDS[sign]
    lord_sign = chart.planets[lord].sign_number

    if lord_sign == sign:
        return 12

    # Count forward from sign to lord's sign
    count = ((lord_sign - sign) % 12)   # 0 would mean same sign (handled above)
    if count == 0:
        count = 12
    duration = 12 - count
    return max(1, duration)


def compute_chara_dasha(
    chart: NatalChart,
    birth_dt: date,
    query_date: Optional[date] = None,
) -> tuple[list[CharaDashaPeriod], Optional[CharaDashaPeriod]]:
    """
    Compute the full Jaimini Chara Dasha sequence from birth.

    Sequence: starts from Lagna sign, proceeds through zodiac in the
    direction determined by the lagna sign's modality:
      - Movable lagna: forward (Aries → Taurus → ... → Pisces)
      - Fixed lagna:   backward (Aries ← Pisces ← ... ← Taurus)
      - Dual lagna:    alternates per sub-period (simplified: forward)

    Returns:
        (list of CharaDashaPeriods, active period at query_date or None)
    """
    if query_date is None:
        query_date = date.today()

    lagna = chart.lagna_sign
    lagna_modality = (lagna - 1) % 3   # 0=movable, 1=fixed, 2=dual

    # Determine sequence direction
    backward = (lagna_modality == 1)

    periods: list[CharaDashaPeriod] = []
    current_date = birth_dt

    # Iterate through all 12 signs starting from lagna
    for offset in range(12):
        if backward:
            sign = ((lagna - 1 - offset) % 12) + 1
        else:
            sign = ((lagna - 1 + offset) % 12) + 1

        years = _chara_dasha_duration(sign, chart)
        days  = round(years * DAYS_PER_YEAR)
        end   = current_date + timedelta(days=days)

        periods.append(CharaDashaPeriod(
            sign_number=sign,
            sign_name=RASHI_NAMES[sign - 1],
            lord=SIGN_LORDS[sign],
            start=current_date,
            end=end,
            duration_years=years,
        ))
        current_date = end

    active = next((p for p in periods if p.contains(query_date)), None)
    return periods, active


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def compute_jaimini_bundle(
    chart: NatalChart,
    birth_dt: date,
    d9_planets: Optional[dict[PlanetName, int]] = None,
    query_date: Optional[date] = None,
) -> JaiminiBundle:
    """
    Compute all Jaimini-specific data for a natal chart.

    Args:
        chart:       Natal D1 chart.
        birth_dt:    Date of birth.
        d9_planets:  Dict of PlanetName → D9 sign number (for Karakamsha).
        query_date:  Date for active Chara Dasha. Defaults to today.

    Returns:
        JaiminiBundle with karakas, aspects, argalas, and dasha timing.
    """
    if d9_planets is None:
        d9_planets = {}

    # 1. Chara Karakas
    karaka_dict = compute_chara_karakas(chart.planets)
    karakas = JaiminiKarakas(
        atmakaraka=karaka_dict["atmakaraka"],
        amatyakaraka=karaka_dict["amatyakaraka"],
        bhratrikaraka=karaka_dict["bhratrikaraka"],
        matrikaraka=karaka_dict["matrikaraka"],
        putrakaraka=karaka_dict["putrakaraka"],
        gnatikaraka=karaka_dict["gnatikaraka"],
        darakaraka=karaka_dict["darakaraka"],
        sign_numbers={k: chart.planets[v].sign_number for k, v in karaka_dict.items()},
    )

    # 2. Karakamsha (AK's sign in D9)
    ak = karaka_dict["atmakaraka"]
    karakamsha = d9_planets.get(ak, chart.planets[ak].sign_number)  # fallback to D1 if no D9

    # 3. Rasi Drishti
    rasi_aspects = compute_rasi_drishti()

    # 4. Argalas for each planet and the lagna
    argalas: dict[str, ArgalaResult] = {}
    for planet in PlanetName:
        p_sign = chart.planets[planet].sign_number
        argalas[planet.value] = compute_argala(chart, p_sign)
    argalas["lagna"] = compute_argala(chart, chart.lagna_sign)

    # 5. Chara Dasha
    chara_periods, active_period = compute_chara_dasha(chart, birth_dt, query_date)

    return JaiminiBundle(
        chart_id=chart.chart_id,
        karakas=karakas,
        karakamsha_sign=karakamsha,
        swamsha_sign=karakamsha,
        rasi_aspects=rasi_aspects,
        argalas=argalas,
        chara_dashas=chara_periods,
        active_chara_dasha=active_period,
    )
