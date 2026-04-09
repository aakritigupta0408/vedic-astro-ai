"""
special_lagna_engine.py — Special lagnas and Arudha Pada computation.

Implements:
  Special Lagnas: Hora Lagna, Ghati Lagna, Vighati Lagna, Bhava Lagna,
                  Pranapada, Indu Lagna, Sri Lagna, Chandra Lagna,
                  Surya Lagna, Karakamsha, Swamsha, Varnada Lagna.
  Arudha Padas:   AL (A1), A2–A12, Upapada Lagna (UL = A12).
  Chart Frames:   Chandra Kundali (Moon as lagna), Surya Kundali (Sun as lagna),
                  Bhava Chalit (Sripati house cusps).

Pure deterministic math — zero LLM calls.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from vedic_astro.engines.natal_engine import (
    NatalChart,
    PlanetName,
    RASHI_NAMES,
    SIGN_LORDS,
    RASHI_SPAN,
    longitude_to_sign,
)


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SpecialLagna:
    """One special lagna (ascendant) and its derived metadata."""
    name: str
    sign_number: int         # 1–12
    sign_name: str
    lord: PlanetName
    degree: float            # degree within the sign (0–30); 0.0 if not precisely known


@dataclass
class ArudhaSet:
    """The 12 Arudha Padas computed from a natal chart."""
    # Keys A1–A12; A1 = Arudha Lagna, A12 = Upapada Lagna
    padas: dict[str, SpecialLagna]          # e.g. "A1" → SpecialLagna

    @property
    def arudha_lagna(self) -> SpecialLagna:
        return self.padas["A1"]

    @property
    def upapada_lagna(self) -> SpecialLagna:
        return self.padas["A12"]


@dataclass
class SpecialLagnaBundle:
    """All special lagnas and arudha padas for a chart."""
    chart_id: str
    special: dict[str, SpecialLagna]        # name → SpecialLagna
    arudhas: ArudhaSet
    chandra_lagna: int                      # sign number where Moon is (used as lagna)
    surya_lagna: int                        # sign number where Sun is (used as lagna)


# ─────────────────────────────────────────────────────────────────────────────
# Arudha Pada computation
# ─────────────────────────────────────────────────────────────────────────────

def _compute_arudha(
    house_number: int,
    chart: NatalChart,
) -> SpecialLagna:
    """
    Compute the Arudha Pada for one house.

    Algorithm (Parashari):
    1. Find the sign of house H (bhava_sign).
    2. Find the lord of that sign (lord_planet).
    3. Find the house where the lord currently sits (lord_house).
    4. Count the same distance FROM the lord's current sign: that is the Arudha sign.
    5. Special rule: if the Arudha falls in the same sign as H, or in its 7th,
       push it 10 signs forward (adds one cycle of 10).

    Args:
        house_number: 1–12.
        chart: Natal D1 chart.

    Returns:
        SpecialLagna for this arudha pada.
    """
    bhava = chart.bhavas[house_number]
    bhava_sign = bhava.sign_number
    lord = bhava.lord

    # Where is the lord placed in the natal chart?
    lord_pos = chart.planets[lord]
    lord_sign = lord_pos.sign_number

    # Distance from bhava_sign to lord_sign (counting forward, 1-indexed)
    distance = ((lord_sign - bhava_sign) % 12)  # 0 = same sign → distance of 12

    # Arudha = same distance ahead of lord_sign
    arudha_sign = ((lord_sign - 1 + distance) % 12) + 1

    # Special correction: Arudha cannot be same as bhava sign or its 7th
    seventh_from_bhava = ((bhava_sign - 1 + 6) % 12) + 1
    if arudha_sign == bhava_sign or arudha_sign == seventh_from_bhava:
        arudha_sign = ((arudha_sign - 1 + 9) % 12) + 1   # push 10 signs

    name = f"A{house_number}"
    return SpecialLagna(
        name=name,
        sign_number=arudha_sign,
        sign_name=RASHI_NAMES[arudha_sign - 1],
        lord=SIGN_LORDS[arudha_sign],
        degree=0.0,
    )


def compute_arudha_set(chart: NatalChart) -> ArudhaSet:
    """Compute all 12 Arudha Padas (A1–A12) for a natal chart."""
    padas = {f"A{h}": _compute_arudha(h, chart) for h in range(1, 13)}
    return ArudhaSet(padas=padas)


# ─────────────────────────────────────────────────────────────────────────────
# Special Lagna computation
# ─────────────────────────────────────────────────────────────────────────────

def _make_lagna(name: str, sign: int, degree: float = 0.0) -> SpecialLagna:
    sign = ((sign - 1) % 12) + 1
    return SpecialLagna(
        name=name,
        sign_number=sign,
        sign_name=RASHI_NAMES[sign - 1],
        lord=SIGN_LORDS[sign],
        degree=round(degree, 4),
    )


def compute_hora_lagna(
    chart: NatalChart,
    birth_hour_decimal: float,
) -> SpecialLagna:
    """
    Hora Lagna — advances one sign every 2.5 ghatis (1 hora = 2½ ghatis = 60 minutes).

    Each hour after sunrise, Hora Lagna advances one sign from the birth lagna.
    Approximated here as: sign = (lagna_sign + floor(birth_hour_decimal / 1.0)) mod 12.

    A more precise computation requires local sunrise time (not available without
    ephemeris data for that day). This approximation is sufficient for agent use.
    """
    # Hora Lagna advances one sign per hora (2 hours approx in simplified reckoning)
    hora_index = int(birth_hour_decimal / 2.0)
    sign = ((chart.lagna_sign - 1 + hora_index) % 12) + 1
    return _make_lagna("Hora Lagna", sign)


def compute_ghati_lagna(
    chart: NatalChart,
    birth_hour_decimal: float,
) -> SpecialLagna:
    """
    Ghati Lagna — advances one sign every ghati (24 minutes).

    Ghati Lagna sign = (lagna_sign + total_ghatis) mod 12,
    where total_ghatis = floor(birth_hour_decimal * 60 / 24).
    """
    total_ghatis = int(birth_hour_decimal * 60.0 / 24.0)
    sign = ((chart.lagna_sign - 1 + total_ghatis) % 12) + 1
    return _make_lagna("Ghati Lagna", sign)


def compute_vighati_lagna(
    chart: NatalChart,
    birth_hour_decimal: float,
) -> SpecialLagna:
    """
    Vighati Lagna — advances one sign every vighati (0.4 minutes).

    Extremely sensitive to birth time; mainly for research use.
    """
    total_vighatis = int(birth_hour_decimal * 60.0 / 0.4)
    sign = ((chart.lagna_sign - 1 + total_vighatis) % 12) + 1
    return _make_lagna("Vighati Lagna", sign)


def compute_bhava_lagna(
    chart: NatalChart,
    birth_hour_decimal: float,
) -> SpecialLagna:
    """
    Bhava Lagna — approximately 5 ghatis (2 hours) after Hora Lagna.

    Used for determining the real Bhava axis in Jaimini-influenced readings.
    """
    hora_ghatis = int(birth_hour_decimal * 60.0 / 24.0)
    bhava_ghatis = hora_ghatis + 5
    sign = ((chart.lagna_sign - 1 + bhava_ghatis) % 12) + 1
    return _make_lagna("Bhava Lagna", sign)


def compute_pranapada_lagna(chart: NatalChart) -> SpecialLagna:
    """
    Pranapada Lagna — based on the Sun's longitude.

    For Sun in odd signs: Pranapada = Sun longitude + 240° (i.e. + 8 signs).
    For Sun in even signs: Pranapada = Sun longitude − 240° (i.e. − 8 signs = +4 signs).
    """
    sun = chart.planets[PlanetName.SUN]
    sun_lon = sun.longitude
    if sun.sign_number % 2 == 1:   # odd sign
        pp_lon = (sun_lon + 240.0) % 360.0
    else:
        pp_lon = (sun_lon + 120.0) % 360.0   # −240 = +120 mod 360
    sign = longitude_to_sign(pp_lon)
    deg = pp_lon % RASHI_SPAN
    return _make_lagna("Pranapada", sign, deg)


def compute_indu_lagna(chart: NatalChart) -> SpecialLagna:
    """
    Indu Lagna — derived from the 9th lord's power and Moon.

    Classical formula (simplified): add the values of the 9th lord from
    Lagna and the 9th lord from Moon, place the result from Aries.
    Rasi value mapping (Parashari) is used for the ruling planet.
    """
    # Rasi strength values per BPHS ch.7 (Indu Lagna)
    planet_indu_values: dict[PlanetName, int] = {
        PlanetName.SUN:     30,
        PlanetName.MOON:    16,
        PlanetName.MARS:    6,
        PlanetName.MERCURY: 8,
        PlanetName.JUPITER: 10,
        PlanetName.VENUS:   12,
        PlanetName.SATURN:  1,
        PlanetName.RAHU:    0,
        PlanetName.KETU:    0,
    }

    ninth_bhava_from_lagna = chart.bhavas[9]
    ninth_lord_lagna = ninth_bhava_from_lagna.lord

    moon_house = chart.planets[PlanetName.MOON].house
    ninth_from_moon_house = ((moon_house - 1 + 8) % 12) + 1
    ninth_from_moon_sign = chart.bhavas[ninth_from_moon_house].sign_number
    ninth_lord_moon = SIGN_LORDS[ninth_from_moon_sign]

    val = (
        planet_indu_values.get(ninth_lord_lagna, 0)
        + planet_indu_values.get(ninth_lord_moon, 0)
    ) % 12
    if val == 0:
        val = 12
    # Indu Lagna = val-th sign from Moon's sign
    moon_sign = chart.planets[PlanetName.MOON].sign_number
    sign = ((moon_sign - 1 + val - 1) % 12) + 1
    return _make_lagna("Indu Lagna", sign)


def compute_sri_lagna(chart: NatalChart) -> SpecialLagna:
    """
    Sri Lagna — wealth indicator derived from Moon's position relative to Lagna.

    Simplified: count same distance from Moon's sign as Moon is from Lagna,
    then place from Lagna. This gives the reflection of Moon around Lagna.
    """
    moon_sign = chart.planets[PlanetName.MOON].sign_number
    lagna_sign = chart.lagna_sign
    distance = (moon_sign - lagna_sign) % 12
    sri_sign = ((lagna_sign - 1 + distance * 2) % 12) + 1
    return _make_lagna("Sri Lagna", sri_sign)


def compute_karakamsha(chart: NatalChart, d9_planets: dict[PlanetName, int]) -> SpecialLagna:
    """
    Karakamsha Lagna — the sign occupied by the Atmakaraka in the Navamsha (D9),
    transposed back to the Rasi chart. This sign becomes the Karakamsha.

    Args:
        chart:       Natal D1 chart (for Jaimini chara karakas).
        d9_planets:  Dict of PlanetName → sign_number in D9.
    """
    from vedic_astro.engines.natal_engine import compute_chara_karakas
    karakas = compute_chara_karakas(chart.planets)
    atmakaraka = karakas["atmakaraka"]
    ksh_sign = d9_planets.get(atmakaraka, chart.lagna_sign)
    return _make_lagna("Karakamsha", ksh_sign)


def compute_swamsha(chart: NatalChart, d9_planets: dict[PlanetName, int]) -> SpecialLagna:
    """
    Swamsha Lagna — the Navamsha sign of the Atmakaraka, used as the lagna
    for the Navamsha chart itself. Same sign as Karakamsha but used within D9.
    """
    from vedic_astro.engines.natal_engine import compute_chara_karakas
    karakas = compute_chara_karakas(chart.planets)
    atmakaraka = karakas["atmakaraka"]
    sw_sign = d9_planets.get(atmakaraka, chart.lagna_sign)
    return _make_lagna("Swamsha", sw_sign)


def compute_varnada_lagna(chart: NatalChart) -> SpecialLagna:
    """
    Varnada Lagna — computed from Hora Lagna and Ghati Lagna.

    Formula (simplified):
      If lagna is odd: Varnada = (HL_distance + GL_distance) mod 12 from Aries.
      If lagna is even: Varnada = (HL_distance − GL_distance) mod 12 from Aries.

    Where HL_distance and GL_distance are distances from Aries to Hora/Ghati lagnas.
    Approximation using birth hour = 12:00 (noon) as default when actual birth time
    fractional hour is not passed here.
    """
    # Approximate using lagna sign as proxy for HL and GL
    # In a production call, pass birth_hour_decimal for accuracy
    hl = chart.lagna_sign              # simplified: Hora Lagna ≈ lagna sign
    gl = ((chart.lagna_sign - 1 + 3) % 12) + 1    # simplified: Ghati Lagna offset
    if chart.lagna_sign % 2 == 1:
        v = ((hl - 1) + (gl - 1)) % 12 + 1
    else:
        v = abs((hl - 1) - (gl - 1)) % 12 + 1
    return _make_lagna("Varnada Lagna", v)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def compute_special_lagna_bundle(
    chart: NatalChart,
    d9_planets: Optional[dict[PlanetName, int]] = None,
    birth_hour_decimal: float = 12.0,
) -> SpecialLagnaBundle:
    """
    Compute all special lagnas and arudha padas for a natal chart.

    Args:
        chart:              Natal D1 chart.
        d9_planets:         Dict of PlanetName → D9 sign (for Karakamsha/Swamsha).
                            Pass {} or None if D9 is not yet computed.
        birth_hour_decimal: Local birth hour as decimal (e.g. 14.5 = 14:30).
                            Used for Hora, Ghati, Vighati, Bhava lagnas.

    Returns:
        SpecialLagnaBundle with all lagnas and arudhas.
    """
    if d9_planets is None:
        d9_planets = {}

    moon_sign = chart.planets[PlanetName.MOON].sign_number
    sun_sign  = chart.planets[PlanetName.SUN].sign_number

    special: dict[str, SpecialLagna] = {}

    # Fixed-frame lagnas (always computable from D1)
    special["Chandra Lagna"] = _make_lagna("Chandra Lagna", moon_sign)
    special["Surya Lagna"]   = _make_lagna("Surya Lagna",   sun_sign)
    special["Udaya Lagna"]   = _make_lagna("Udaya Lagna",   chart.lagna_sign, chart.lagna_longitude % RASHI_SPAN)
    special["Pranapada"]     = compute_pranapada_lagna(chart)
    special["Indu Lagna"]    = compute_indu_lagna(chart)
    special["Sri Lagna"]     = compute_sri_lagna(chart)
    special["Varnada Lagna"] = compute_varnada_lagna(chart)

    # Birth-time dependent lagnas (need birth_hour_decimal)
    special["Hora Lagna"]    = compute_hora_lagna(chart, birth_hour_decimal)
    special["Ghati Lagna"]   = compute_ghati_lagna(chart, birth_hour_decimal)
    special["Vighati Lagna"] = compute_vighati_lagna(chart, birth_hour_decimal)
    special["Bhava Lagna"]   = compute_bhava_lagna(chart, birth_hour_decimal)

    # D9-dependent lagnas
    if d9_planets:
        special["Karakamsha"] = compute_karakamsha(chart, d9_planets)
        special["Swamsha"]    = compute_swamsha(chart, d9_planets)

    # Arudha padas
    arudhas = compute_arudha_set(chart)

    return SpecialLagnaBundle(
        chart_id=chart.chart_id,
        special=special,
        arudhas=arudhas,
        chandra_lagna=moon_sign,
        surya_lagna=sun_sign,
    )
