"""
transit_engine.py — Live planetary transit computation engine.

Pure deterministic math — zero LLM calls.
Computes current planetary positions (gochara) for any date and overlays
them on a natal chart to produce transit aspects and gochara strength.

Architecture correction applied:
    - TransitSnapshot does NOT contain natal-specific data (aspects_over_natal).
    - Aspects over natal are computed SEPARATELY as TransitOverlay, which is
      user-specific and cached with a composite key (chart_id + date).
    - Transit cache is split:
        fast_transit (Moon): TTL = 1 hour  (Moon moves ~0.55°/hour)
        slow_transit (rest): TTL = 24 hours (outer planets negligible daily change)
    - Gochara evaluates from BOTH natal Moon and Lagna (architecture correction #6).

Caching strategy:
    TransitSnapshot   key: "transit_slow:v1:<YYYY-MM-DD>"      TTL: 24h (shared globally)
                      key: "transit_moon:v1:<YYYY-MM-DD-HH>"   TTL: 1h  (Moon only)
    TransitOverlay    key: "overlay:v1:<chart_id>:<YYYY-MM-DD>" TTL: 24h (user-specific)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Optional

import swisseph as swe

from vedic_astro.engines.natal_engine import (
    AyanamshaType,
    BhavaData,
    NatalChart,
    NakshatraData,
    PlanetName,
    PlanetPosition,
    compute_ayanamsha,
    compute_julian_day,
    compute_nakshatra,
    compute_planet_positions,
    longitude_to_sign,
    RASHI_NAMES,
    RASHI_SPAN,
    NAKSHATRA_SPAN,
    SIGN_LORDS,
)

# ─────────────────────────────────────────────────────────────────────────────
# Gochara strength tables (classical Vedic — from Moon sign)
# ─────────────────────────────────────────────────────────────────────────────
# Source: Brihat Parashara Hora Shastra, Phaladeepika
# Value: 1.0 = fully favorable, 0.0 = unfavorable
# House from natal Moon (1–12)

GOCHARA_FROM_MOON: dict[PlanetName, dict[int, float]] = {
    PlanetName.SUN: {
        1: 0.0, 2: 0.0, 3: 1.0, 4: 0.0, 5: 0.0, 6: 1.0,
        7: 0.0, 8: 0.0, 9: 0.0, 10: 0.0, 11: 1.0, 12: 0.0,
    },
    PlanetName.MOON: {
        1: 1.0, 2: 0.0, 3: 1.0, 4: 0.0, 5: 0.0, 6: 0.0,
        7: 1.0, 8: 0.0, 9: 1.0, 10: 0.0, 11: 1.0, 12: 0.0,
    },
    PlanetName.MARS: {
        1: 0.0, 2: 0.0, 3: 1.0, 4: 0.0, 5: 0.0, 6: 1.0,
        7: 0.0, 8: 0.0, 9: 0.0, 10: 0.0, 11: 1.0, 12: 0.0,
    },
    PlanetName.MERCURY: {
        1: 0.0, 2: 1.0, 3: 1.0, 4: 0.0, 5: 1.0, 6: 0.0,
        7: 0.0, 8: 0.0, 9: 1.0, 10: 1.0, 11: 1.0, 12: 0.0,
    },
    PlanetName.JUPITER: {
        1: 0.0, 2: 1.0, 3: 0.0, 4: 0.0, 5: 1.0, 6: 0.0,
        7: 1.0, 8: 0.0, 9: 1.0, 10: 0.0, 11: 1.0, 12: 0.0,
    },
    PlanetName.VENUS: {
        1: 1.0, 2: 1.0, 3: 0.0, 4: 1.0, 5: 1.0, 6: 0.0,
        7: 0.0, 8: 1.0, 9: 0.0, 10: 0.0, 11: 0.0, 12: 1.0,
    },
    PlanetName.SATURN: {
        1: 0.0, 2: 0.0, 3: 1.0, 4: 0.0, 5: 0.0, 6: 1.0,
        7: 0.0, 8: 0.0, 9: 0.0, 10: 0.0, 11: 1.0, 12: 1.0,
    },
    PlanetName.RAHU: {
        1: 0.0, 2: 0.0, 3: 1.0, 4: 0.0, 5: 0.0, 6: 1.0,
        7: 0.0, 8: 0.0, 9: 0.0, 10: 0.0, 11: 1.0, 12: 0.0,
    },
    PlanetName.KETU: {
        1: 0.0, 2: 0.0, 3: 1.0, 4: 0.0, 5: 0.0, 6: 1.0,
        7: 0.0, 8: 0.0, 9: 0.0, 10: 0.0, 11: 1.0, 12: 0.0,
    },
}

# Gochara from Lagna (less documented classically; use simplified benefic/malefic house rules)
GOCHARA_FROM_LAGNA: dict[PlanetName, dict[int, float]] = {
    PlanetName.JUPITER: {
        1: 1.0, 2: 1.0, 3: 0.5, 4: 0.5, 5: 1.0, 6: 0.0,
        7: 1.0, 8: 0.0, 9: 1.0, 10: 1.0, 11: 1.0, 12: 0.0,
    },
    PlanetName.SATURN: {
        1: 0.0, 2: 0.0, 3: 1.0, 4: 0.0, 5: 0.0, 6: 1.0,
        7: 0.0, 8: 0.0, 9: 0.0, 10: 1.0, 11: 1.0, 12: 0.5,
    },
    PlanetName.RAHU: {
        1: 0.0, 2: 0.0, 3: 1.0, 4: 0.0, 5: 0.0, 6: 1.0,
        7: 0.0, 8: 0.0, 9: 0.0, 10: 1.0, 11: 1.0, 12: 0.0,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Aspect definitions (Vedic drishti)
# ─────────────────────────────────────────────────────────────────────────────

class AspectType(str, Enum):
    FULL    = "full"        # 7th house drishti (all planets)
    SPECIAL = "special"     # Additional aspects: Mars(4,8), Jupiter(5,9), Saturn(3,10)


# Special aspect houses (in addition to universal 7th aspect)
_SPECIAL_ASPECTS: dict[PlanetName, list[int]] = {
    PlanetName.MARS:    [4, 8],   # 4th and 8th from Mars
    PlanetName.JUPITER: [5, 9],   # 5th and 9th from Jupiter
    PlanetName.SATURN:  [3, 10],  # 3rd and 10th from Saturn
    PlanetName.RAHU:    [5, 9],   # conventional (school-dependent)
    PlanetName.KETU:    [5, 9],   # conventional (school-dependent)
}


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TransitPosition:
    """Current sidereal position of a planet at a given date."""
    planet: PlanetName
    longitude: float
    sign_number: int
    sign_name: str
    degree_in_sign: float
    is_retrograde: bool
    speed: float
    nakshatra: NakshatraData


@dataclass(frozen=True)
class TransitSnapshot:
    """
    All planetary positions at a given date.

    Globally cacheable — contains NO natal-specific data.
    Two users born on different dates but querying the same date
    will share this exact snapshot from cache.
    """
    snapshot_date: date
    ayanamsha: AyanamshaType
    ayanamsha_value: float
    positions: dict[PlanetName, TransitPosition]


@dataclass(frozen=True)
class GocharyaStrength:
    """
    Gochara (transit) strength for a single planet.

    Evaluates from BOTH natal Moon and Lagna as per classical dual reference.
    """
    planet: PlanetName
    house_from_moon: int
    house_from_lagna: int
    strength_from_moon: float    # 0.0–1.0
    strength_from_lagna: float   # 0.0–1.0
    composite_strength: float    # weighted average (Moon primary: 0.6, Lagna: 0.4)
    is_favorable: bool           # composite_strength >= 0.5


@dataclass
class TransitAspect:
    """
    A transit planet's aspect over a natal planet or house.
    Computed per-user; NOT part of the globally-cached TransitSnapshot.
    """
    transit_planet: PlanetName
    aspect_type: AspectType
    aspected_house: int                           # in natal chart (1–12)
    aspected_natal_planet: Optional[PlanetName]   # None if aspecting empty house
    transit_sign: int
    natal_sign: int
    is_applying: bool                             # True if orb is decreasing


@dataclass
class TransitOverlay:
    """
    Transit-over-natal analysis for a specific user and date.

    User-specific — cached with composite key (chart_id + date).
    Separated from TransitSnapshot to prevent cross-user cache contamination.
    """
    chart_id: str
    overlay_date: date
    snapshot: TransitSnapshot
    gochara: dict[PlanetName, GocharyaStrength]
    aspects: list[TransitAspect]
    sadesati_active: bool                  # Saturn within 3 signs of natal Moon
    sadesati_phase: Optional[str]          # "rising", "peak", "setting", None


# ─────────────────────────────────────────────────────────────────────────────
# Core computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_transit_snapshot(
    query_date: date,
    ayanamsha: AyanamshaType = AyanamshaType.LAHIRI,
    query_time: time = time(0, 0, 0),
) -> TransitSnapshot:
    """
    Compute sidereal planetary positions for a given date.

    This result is globally cacheable — it contains no natal-specific information.
    The cache decorator (applied in pipeline.py) uses the date + ayanamsha as key.

    Args:
        query_date:  Date for which to compute transits.
        ayanamsha:   Ayanamsha system.
        query_time:  Time of day (UTC). Defaults to midnight.
                     For Moon, use actual query time for accuracy.

    Returns:
        TransitSnapshot with all 9 Navagraha positions.
    """
    dt_utc = datetime(
        query_date.year, query_date.month, query_date.day,
        query_time.hour, query_time.minute, query_time.second,
        tzinfo=timezone.utc,
    )
    jd = compute_julian_day(dt_utc)
    ayanamsha_value = compute_ayanamsha(jd, ayanamsha)

    raw_data = compute_planet_positions(jd, ayanamsha_value)

    positions: dict[PlanetName, TransitPosition] = {}
    for planet, (lon, speed, is_retro) in raw_data.items():
        sign_num = longitude_to_sign(lon)
        deg_in_sign = lon % RASHI_SPAN
        nak = compute_nakshatra(lon)
        positions[planet] = TransitPosition(
            planet=planet,
            longitude=round(lon, 6),
            sign_number=sign_num,
            sign_name=RASHI_NAMES[sign_num - 1],
            degree_in_sign=round(deg_in_sign, 4),
            is_retrograde=is_retro,
            speed=round(speed, 6),
            nakshatra=nak,
        )

    return TransitSnapshot(
        snapshot_date=query_date,
        ayanamsha=ayanamsha,
        ayanamsha_value=round(ayanamsha_value, 6),
        positions=positions,
    )


def _house_distance(from_sign: int, to_sign: int) -> int:
    """
    Compute the house number of to_sign relative to from_sign.
    (Whole-sign system: from_sign = house 1)
    Returns 1–12.
    """
    return ((to_sign - from_sign) % 12) + 1


def compute_gochara_strength(
    transit_planet: PlanetName,
    transit_sign: int,
    natal_moon_sign: int,
    natal_lagna_sign: int,
) -> GocharyaStrength:
    """
    Compute gochara (transit) strength for a planet relative to natal Moon and Lagna.

    Architecture correction: evaluates from BOTH Moon (primary) and Lagna (secondary).

    Args:
        transit_planet:    The transiting graha.
        transit_sign:      Sign the planet is transiting (1–12).
        natal_moon_sign:   Natal Moon's sign (Janma Rashi).
        natal_lagna_sign:  Natal Ascendant sign.

    Returns:
        GocharyaStrength with composite score and favorable/unfavorable flag.
    """
    house_from_moon   = _house_distance(natal_moon_sign, transit_sign)
    house_from_lagna  = _house_distance(natal_lagna_sign, transit_sign)

    moon_table  = GOCHARA_FROM_MOON.get(transit_planet, {})
    lagna_table = GOCHARA_FROM_LAGNA.get(transit_planet, {})

    strength_moon  = moon_table.get(house_from_moon, 0.5)
    strength_lagna = lagna_table.get(house_from_lagna, 0.5)

    # Moon is primary reference (60%), Lagna secondary (40%)
    # If no lagna-specific table exists, weight 100% on Moon
    if lagna_table:
        composite = 0.6 * strength_moon + 0.4 * strength_lagna
    else:
        composite = strength_moon

    return GocharyaStrength(
        planet=transit_planet,
        house_from_moon=house_from_moon,
        house_from_lagna=house_from_lagna,
        strength_from_moon=strength_moon,
        strength_from_lagna=strength_lagna,
        composite_strength=round(composite, 3),
        is_favorable=composite >= 0.5,
    )


def compute_transit_aspects(
    snapshot: TransitSnapshot,
    natal_chart: NatalChart,
) -> list[TransitAspect]:
    """
    Compute all transit planet aspects over natal planet positions and houses.

    Each planet aspects the 7th house from itself (full drishti).
    Mars additionally aspects 4th and 8th; Jupiter 5th and 9th; Saturn 3rd and 10th.

    Args:
        snapshot:     Current transit positions.
        natal_chart:  Natal chart to overlay transits upon.

    Returns:
        List of TransitAspect objects (one per aspected house/planet combination).
    """
    aspects: list[TransitAspect] = []
    natal_lagna_sign = natal_chart.lagna_sign

    for transit_planet, transit_pos in snapshot.positions.items():
        t_sign = transit_pos.sign_number
        t_house_from_lagna = _house_distance(natal_lagna_sign, t_sign)

        # Collect all houses this planet aspects (from its transit house)
        aspected_houses_offsets = [7]  # 7th aspect = universal
        special = _SPECIAL_ASPECTS.get(transit_planet, [])
        all_offsets = aspected_houses_offsets + special

        for offset in all_offsets:
            aspected_house = ((t_house_from_lagna - 1 + offset - 1) % 12) + 1
            aspected_sign = ((natal_lagna_sign - 1 + aspected_house - 1) % 12) + 1

            # Find natal planet in this house (if any)
            aspected_planet = None
            for np, npos in natal_chart.planets.items():
                if npos.house == aspected_house:
                    aspected_planet = np
                    break  # take first occupant (report all in production)

            aspect_type = AspectType.FULL if offset == 7 else AspectType.SPECIAL

            # Is aspect applying? (transit planet moving toward the aspected sign)
            # Simplified: if speed > 0 (direct), planet moving forward through signs
            is_applying = transit_pos.speed > 0

            aspects.append(TransitAspect(
                transit_planet=transit_planet,
                aspect_type=aspect_type,
                aspected_house=aspected_house,
                aspected_natal_planet=aspected_planet,
                transit_sign=t_sign,
                natal_sign=aspected_sign,
                is_applying=is_applying,
            ))

    return aspects


def _check_sadesati(
    saturn_sign: int,
    natal_moon_sign: int,
) -> tuple[bool, Optional[str]]:
    """
    Check if Sade Sati (7.5-year Saturn cycle) is active.

    Saturn in the sign before, the sign of, or the sign after natal Moon
    constitutes Sade Sati. Three 2.5-year phases.

    Returns:
        (is_active, phase) where phase is "rising", "peak", or "setting".
    """
    before_moon = ((natal_moon_sign - 2) % 12) + 1
    after_moon  = (natal_moon_sign % 12) + 1

    if saturn_sign == before_moon:
        return True, "rising"
    if saturn_sign == natal_moon_sign:
        return True, "peak"
    if saturn_sign == after_moon:
        return True, "setting"
    return False, None


def compute_transit_overlay(
    snapshot: TransitSnapshot,
    natal_chart: NatalChart,
) -> TransitOverlay:
    """
    Compute the full transit overlay for a specific natal chart.

    This is the user-specific computation that must NOT be globally cached.
    Cache key: "overlay:v1:<chart_id>:<snapshot_date>" with 24h TTL.

    Args:
        snapshot:     Global transit snapshot for the query date.
        natal_chart:  The user's natal chart.

    Returns:
        TransitOverlay with gochara strengths, aspects, and Sade Sati status.
    """
    natal_moon_sign  = natal_chart.planets[PlanetName.MOON].sign_number
    natal_lagna_sign = natal_chart.lagna_sign

    # Gochara strength for each transit planet
    gochara: dict[PlanetName, GocharyaStrength] = {}
    for planet, transit_pos in snapshot.positions.items():
        gochara[planet] = compute_gochara_strength(
            planet,
            transit_pos.sign_number,
            natal_moon_sign,
            natal_lagna_sign,
        )

    # Transit aspects over natal chart
    aspects = compute_transit_aspects(snapshot, natal_chart)

    # Sade Sati check
    saturn_sign = snapshot.positions[PlanetName.SATURN].sign_number
    sadesati_active, sadesati_phase = _check_sadesati(saturn_sign, natal_moon_sign)

    return TransitOverlay(
        chart_id=natal_chart.chart_id,
        overlay_date=snapshot.snapshot_date,
        snapshot=snapshot,
        gochara=gochara,
        aspects=aspects,
        sadesati_active=sadesati_active,
        sadesati_phase=sadesati_phase,
    )


def get_transits_for_date(
    query_date: Optional[date] = None,
    ayanamsha: AyanamshaType = AyanamshaType.LAHIRI,
) -> TransitSnapshot:
    """
    Convenience wrapper: get transit snapshot for today (or given date).

    Args:
        query_date: Target date. Defaults to today.
        ayanamsha:  Ayanamsha system.

    Returns:
        TransitSnapshot for the given date.
    """
    if query_date is None:
        query_date = date.today()
    return compute_transit_snapshot(query_date, ayanamsha)
