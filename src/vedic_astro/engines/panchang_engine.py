"""
panchang_engine.py — Vedic Panchang computation engine.

Pure deterministic math — zero LLM calls.
Computes the five limbs (Pancha Anga) of the Vedic calendar for any date:
    1. Tithi    — Lunar day (1–30, Shukla/Krishna paksha)
    2. Vara     — Weekday with planetary lord
    3. Nakshatra — Moon's nakshatra with pada
    4. Yoga     — Nithya Yoga (27 types from Sun+Moon longitude)
    5. Karana   — Half-tithi (11 types)

Architecture correction applied:
    - Panchang Yoga (Nithya Yoga) is renamed to `NithyaYoga` throughout
      to prevent naming collision with astrological yogas (Gajakesari, etc.)
    - Class is NithyaYoga, not Yoga.

Caching strategy:
    Cache key: "panchang:v1:<YYYY-MM-DD>:<lat_3dp>:<lon_3dp>"
    TTL: 24 hours
    Lat/lon truncated to 3 decimal places (~100m precision) for cache sharing
    across users in the same city without meaningful panchang difference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Optional

import swisseph as swe

from vedic_astro.engines.natal_engine import (
    AyanamshaType,
    NakshatraData,
    PlanetName,
    NAKSHATRA_NAMES,
    NAKSHATRA_SPAN,
    PADA_SPAN,
    compute_ayanamsha,
    compute_julian_day,
    compute_planet_positions,
    tropical_to_sidereal,
)
from vedic_astro.engines.dasha_engine import NAKSHATRA_LORDS

# ─────────────────────────────────────────────────────────────────────────────
# Tithi
# ─────────────────────────────────────────────────────────────────────────────

TITHI_NAMES: list[str] = [
    # Shukla Paksha (1–15)
    "Pratipada", "Dvitiya", "Tritiya", "Chaturthi", "Panchami",
    "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami",
    "Ekadashi", "Dvadashi", "Trayodashi", "Chaturdashi", "Purnima",
    # Krishna Paksha (16–30, index 15–29)
    "Pratipada", "Dvitiya", "Tritiya", "Chaturthi", "Panchami",
    "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami",
    "Ekadashi", "Dvadashi", "Trayodashi", "Chaturdashi", "Amavasya",
]

# Tithi lords (Shukla 1–15, Krishna 1–15)
TITHI_LORDS: list[PlanetName] = [
    PlanetName.SUN, PlanetName.MOON, PlanetName.MARS, PlanetName.MERCURY,
    PlanetName.JUPITER, PlanetName.VENUS, PlanetName.SATURN,
    PlanetName.SUN, PlanetName.MOON, PlanetName.MARS, PlanetName.MERCURY,
    PlanetName.JUPITER, PlanetName.VENUS, PlanetName.SATURN, PlanetName.SUN,
]

TITHI_SPAN = 12.0  # degrees of Sun-Moon angle per tithi


@dataclass(frozen=True)
class Tithi:
    """Represents a Vedic lunar day."""
    index: int           # 0-based (0=Shukla Pratipada … 29=Amavasya)
    number: int          # 1–15 within paksha
    name: str            # e.g. "Panchami"
    paksha: str          # "shukla" or "krishna"
    lord: PlanetName
    elapsed_degrees: float   # Sun-Moon angle elapsed within this tithi (0–12°)
    elapsed_percent: float   # 0–100


def compute_tithi(sun_lon: float, moon_lon: float) -> Tithi:
    """
    Compute the current Tithi from sidereal Sun and Moon longitudes.

    Tithi = 1 unit for every 12° of Moon's gain over Sun.
    Total 30 tithis per synodic month (360° / 12° = 30).

    Args:
        sun_lon:  Sidereal Sun longitude (0–360°).
        moon_lon: Sidereal Moon longitude (0–360°).

    Returns:
        Tithi dataclass with index, name, paksha, lord, and elapsed fraction.
    """
    sun_moon_diff = (moon_lon - sun_lon) % 360.0
    tithi_index = int(sun_moon_diff / TITHI_SPAN)  # 0–29
    elapsed_in_tithi = sun_moon_diff % TITHI_SPAN
    elapsed_percent = (elapsed_in_tithi / TITHI_SPAN) * 100.0

    paksha = "shukla" if tithi_index < 15 else "krishna"
    number_in_paksha = (tithi_index % 15) + 1
    name = TITHI_NAMES[tithi_index]
    lord_index = tithi_index % 15
    lord = TITHI_LORDS[lord_index]

    return Tithi(
        index=tithi_index,
        number=number_in_paksha,
        name=name,
        paksha=paksha,
        lord=lord,
        elapsed_degrees=round(elapsed_in_tithi, 4),
        elapsed_percent=round(elapsed_percent, 2),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Vara (weekday)
# ─────────────────────────────────────────────────────────────────────────────

VARA_NAMES: list[str] = [
    "Ravivara", "Somavara", "Mangalavara", "Budhavara",
    "Guruvara", "Shukravara", "Shanivara",
]

VARA_LORDS: list[PlanetName] = [
    PlanetName.SUN, PlanetName.MOON, PlanetName.MARS, PlanetName.MERCURY,
    PlanetName.JUPITER, PlanetName.VENUS, PlanetName.SATURN,
]

VARA_ENGLISH: list[str] = [
    "Sunday", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday",
]


@dataclass(frozen=True)
class Vara:
    """Vedic weekday with ruling planet."""
    weekday_index: int   # 0=Sunday … 6=Saturday
    name: str            # Vedic name
    english: str
    lord: PlanetName


def compute_vara(query_date: date) -> Vara:
    """
    Compute the Vara (weekday) for a given date.

    Python's date.weekday() returns 0=Monday. We adjust to 0=Sunday.

    Args:
        query_date: The date to compute Vara for.

    Returns:
        Vara dataclass.
    """
    # date.isoweekday(): 1=Monday … 7=Sunday → convert to 0=Sunday … 6=Saturday
    iso_weekday = query_date.isoweekday()   # 1–7
    weekday_index = iso_weekday % 7          # 0=Sunday, 1=Monday, ..., 6=Saturday

    return Vara(
        weekday_index=weekday_index,
        name=VARA_NAMES[weekday_index],
        english=VARA_ENGLISH[weekday_index],
        lord=VARA_LORDS[weekday_index],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Nakshatra (from Moon longitude)
# ─────────────────────────────────────────────────────────────────────────────

def compute_nakshatra_from_moon(moon_lon: float) -> NakshatraData:
    """
    Compute the current Nakshatra from Moon's sidereal longitude.

    The Moon's nakshatra is the primary Panchang nakshatra. Other planets'
    nakshatras are computed the same way but are used in natal analysis.

    Args:
        moon_lon: Sidereal Moon longitude (0–360°).

    Returns:
        NakshatraData with index, name, lord, pada, and elapsed fraction.
    """
    from vedic_astro.engines.natal_engine import compute_nakshatra
    return compute_nakshatra(moon_lon)


# ─────────────────────────────────────────────────────────────────────────────
# Nithya Yoga (panchang yoga — 27 types)
# Architecture correction: renamed from Yoga → NithyaYoga to prevent
# collision with astrological yoga terminology.
# ─────────────────────────────────────────────────────────────────────────────

NITHYA_YOGA_NAMES: list[str] = [
    "Vishkambha", "Preeti", "Ayushman", "Saubhagya", "Shobhana",
    "Atiganda", "Sukarma", "Dhriti", "Shula", "Ganda",
    "Vriddhi", "Dhruva", "Vyaghata", "Harshana", "Vajra",
    "Siddhi", "Vyatipata", "Variyan", "Parigha", "Shiva",
    "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma",
    "Mahendra", "Vaidhriti",
]

# Classical nature of each Nithya Yoga (1=benefic, 0=malefic, 0.5=mixed)
NITHYA_YOGA_NATURE: list[str] = [
    "malefic",  "benefic",  "benefic",  "benefic",  "benefic",
    "malefic",  "benefic",  "benefic",  "malefic",  "malefic",
    "benefic",  "benefic",  "malefic",  "benefic",  "malefic",
    "benefic",  "malefic",  "mixed",    "malefic",  "benefic",
    "benefic",  "benefic",  "benefic",  "benefic",  "benefic",
    "benefic",  "malefic",
]

NITHYA_YOGA_SPAN = 360.0 / 27   # = 13.333...° (same as nakshatra span)


@dataclass(frozen=True)
class NithyaYoga:
    """
    One of the 27 Nithya Yogas (astronomical yoga from Sun+Moon longitude sum).

    IMPORTANT: This is NOT the same as astrological yogas (Gajakesari, etc.).
    This is purely a Panchang element computed from Sun+Moon positions.
    Renamed from 'Yoga' to 'NithyaYoga' to prevent naming collision.
    """
    index: int           # 0-based (0=Vishkambha … 26=Vaidhriti)
    name: str
    nature: str          # "benefic", "malefic", or "mixed"
    elapsed_degrees: float
    elapsed_percent: float


def compute_nithya_yoga(sun_lon: float, moon_lon: float) -> NithyaYoga:
    """
    Compute the Nithya Yoga from Sun and Moon sidereal longitudes.

    Formula: yoga_index = floor((sun_lon + moon_lon) % 360 / 13.333...)

    Args:
        sun_lon:  Sidereal Sun longitude (0–360°).
        moon_lon: Sidereal Moon longitude (0–360°).

    Returns:
        NithyaYoga dataclass.
    """
    combined = (sun_lon + moon_lon) % 360.0
    yoga_index = int(combined / NITHYA_YOGA_SPAN) % 27
    elapsed = combined % NITHYA_YOGA_SPAN
    elapsed_percent = (elapsed / NITHYA_YOGA_SPAN) * 100.0

    return NithyaYoga(
        index=yoga_index,
        name=NITHYA_YOGA_NAMES[yoga_index],
        nature=NITHYA_YOGA_NATURE[yoga_index],
        elapsed_degrees=round(elapsed, 4),
        elapsed_percent=round(elapsed_percent, 2),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Karana (half-tithi)
# ─────────────────────────────────────────────────────────────────────────────

# 7 movable karanas (repeat through the month)
MOVABLE_KARANA_NAMES: list[str] = [
    "Bava", "Balava", "Kaulava", "Taitila", "Garaja", "Vanija", "Vishti",
]

MOVABLE_KARANA_LORDS: list[PlanetName] = [
    PlanetName.SUN, PlanetName.MOON, PlanetName.MARS, PlanetName.MERCURY,
    PlanetName.JUPITER, PlanetName.VENUS, PlanetName.SATURN,
]

# 4 fixed karanas (occur once per month at specific positions)
# Position: karana sequence number (0-based, each tithi has 2 karanas, 30 tithis = 60 karanas)
FIXED_KARANAS: dict[int, tuple[str, Optional[PlanetName]]] = {
    0:  ("Kimstughna", None),   # 1st half of Shukla Pratipada
    57: ("Shakuni",    None),   # 1st half of Krishna Chaturdashi
    58: ("Chatushpada",None),   # 2nd half of Krishna Chaturdashi
    59: ("Nagava",     None),   # 1st half of Amavasya
}

KARANA_SPAN = 6.0  # degrees of Sun-Moon angle per karana (half a tithi)


@dataclass(frozen=True)
class Karana:
    """Represents a Vedic half-tithi (Karana)."""
    sequence_number: int   # 0–59 in the lunar month
    name: str
    lord: Optional[PlanetName]
    is_fixed: bool
    elapsed_degrees: float
    elapsed_percent: float


def compute_karana(sun_lon: float, moon_lon: float) -> Karana:
    """
    Compute the current Karana from sidereal Sun and Moon longitudes.

    There are 60 karanas per lunar month (2 per tithi × 30 tithis).
    First karana (seq=0) and last 3 (seq=57,58,59) are fixed.
    The remaining 56 are the 7 movable karanas repeated 8 times.

    Args:
        sun_lon:  Sidereal Sun longitude (0–360°).
        moon_lon: Sidereal Moon longitude (0–360°).

    Returns:
        Karana dataclass.
    """
    sun_moon_diff = (moon_lon - sun_lon) % 360.0
    seq_number = int(sun_moon_diff / KARANA_SPAN)  # 0–59
    elapsed = sun_moon_diff % KARANA_SPAN
    elapsed_percent = (elapsed / KARANA_SPAN) * 100.0

    # Check fixed karanas first
    if seq_number in FIXED_KARANAS:
        name, lord = FIXED_KARANAS[seq_number]
        return Karana(
            sequence_number=seq_number,
            name=name,
            lord=lord,
            is_fixed=True,
            elapsed_degrees=round(elapsed, 4),
            elapsed_percent=round(elapsed_percent, 2),
        )

    # Movable karanas: seq 1–56 map to the 7 movable karanas cycling
    # seq 1 = Bava, seq 2 = Balava, ..., seq 7 = Vishti, seq 8 = Bava, ...
    movable_index = (seq_number - 1) % 7
    name = MOVABLE_KARANA_NAMES[movable_index]
    lord = MOVABLE_KARANA_LORDS[movable_index]

    return Karana(
        sequence_number=seq_number,
        name=name,
        lord=lord,
        is_fixed=False,
        elapsed_degrees=round(elapsed, 4),
        elapsed_percent=round(elapsed_percent, 2),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sunrise / Sunset
# ─────────────────────────────────────────────────────────────────────────────

def compute_sunrise_sunset(
    jd: float,
    lat: float,
    lon: float,
) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Compute sunrise and sunset times for a given date and location.

    Uses Swiss Ephemeris rise/set calculation.

    Args:
        jd:  Julian Day for noon on the target date (approx).
        lat: Geographic latitude (decimal degrees, N positive).
        lon: Geographic longitude (decimal degrees, E positive).

    Returns:
        Tuple of (sunrise_utc, sunset_utc) as datetime objects, or (None, None)
        on failure (e.g., polar regions with no sunrise/sunset).
    """
    def _jd_to_datetime(jd_val: float) -> datetime:
        y, m, d, h = swe.revjul(jd_val)
        total_seconds = h * 3600
        hour = int(total_seconds // 3600)
        minute = int((total_seconds % 3600) // 60)
        second = int(total_seconds % 60)
        return datetime(y, m, d, hour, minute, second, tzinfo=timezone.utc)

    rsmi = swe.CALC_RISE | swe.BIT_DISC_CENTER

    ret_rise, t_rise = swe.rise_trans(jd - 0.5, swe.SUN, rsmi, [lon, lat, 0])
    ret_set,  t_set  = swe.rise_trans(jd - 0.5, swe.SUN, swe.CALC_SET | swe.BIT_DISC_CENTER, [lon, lat, 0])

    sunrise = _jd_to_datetime(t_rise[0]) if ret_rise == 0 else None
    sunset  = _jd_to_datetime(t_set[0])  if ret_set  == 0 else None

    return sunrise, sunset


# ─────────────────────────────────────────────────────────────────────────────
# Hora
# ─────────────────────────────────────────────────────────────────────────────

# Hora lord sequence starting from each weekday (Chaldean order)
# Sun, Venus, Mercury, Moon, Saturn, Jupiter, Mars (repeating)
HORA_SEQUENCE: list[PlanetName] = [
    PlanetName.SUN, PlanetName.VENUS, PlanetName.MERCURY, PlanetName.MOON,
    PlanetName.SATURN, PlanetName.JUPITER, PlanetName.MARS,
]

# First hora lord of each weekday (Sunday=0 … Saturday=6)
VARA_FIRST_HORA: dict[int, int] = {
    0: 0,  # Sunday:    Sun (index 0)
    1: 3,  # Monday:    Moon (index 3)
    2: 6,  # Tuesday:   Mars (index 6)
    3: 2,  # Wednesday: Mercury (index 2)
    4: 5,  # Thursday:  Jupiter (index 5)
    5: 1,  # Friday:    Venus (index 1)
    6: 4,  # Saturday:  Saturn (index 4)
}


def compute_hora_lord(
    query_datetime: datetime,
    sunrise: datetime,
    vara: Vara,
) -> PlanetName:
    """
    Compute the planetary lord of the current Hora (planetary hour).

    Daylight is divided into 12 equal hours; night into 12 equal hours.
    Each hour is ruled by a planet in the Chaldean order.

    Args:
        query_datetime: The query time (UTC).
        sunrise:        Sunrise time (UTC) for the query date.
        vara:           The Vara for the query date.

    Returns:
        PlanetName of the current Hora lord.
    """
    elapsed_seconds = (query_datetime - sunrise).total_seconds()
    # Each hora = 3600 seconds (approximate; full implementation uses dynamic solar hora)
    hora_number = int(elapsed_seconds / 3600) % 24
    if hora_number < 0:
        hora_number += 24

    first_hora_index = VARA_FIRST_HORA[vara.weekday_index]
    hora_index = (first_hora_index + hora_number) % 7
    return HORA_SEQUENCE[hora_index]


# ─────────────────────────────────────────────────────────────────────────────
# Panchang data class
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PanchangData:
    """
    Complete Panchang (five-limb almanac) for a given date and location.

    All values are computed deterministically from astronomical positions.
    Cached with key: "panchang:v1:<date>:<lat_3dp>:<lon_3dp>"
    """
    panchang_date: date
    lat: float
    lon: float
    ayanamsha: AyanamshaType

    # Five limbs
    tithi: Tithi
    vara: Vara
    nakshatra: NakshatraData    # Moon's nakshatra
    nithya_yoga: NithyaYoga     # Note: NithyaYoga, NOT astrological yoga
    karana: Karana

    # Supporting data
    sunrise_utc: Optional[datetime]
    sunset_utc: Optional[datetime]
    hora_lord: Optional[PlanetName]      # Planetary lord of current hora

    # Raw longitudes (useful for downstream computation)
    sun_longitude: float
    moon_longitude: float


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def compute_panchang(
    query_date: date,
    lat: float,
    lon: float,
    ayanamsha: AyanamshaType = AyanamshaType.LAHIRI,
    query_time: Optional[time] = None,
) -> PanchangData:
    """
    Compute the full Panchang for a given date and geographic location.

    Cache: Caller applies @cached_panchang decorator.
    Key: "panchang:v1:<date>:<lat:.3f>:<lon:.3f>"
    TTL: 24 hours (panchang values are date-specific)

    Args:
        query_date:  The date for Panchang computation.
        lat:         Geographic latitude (decimal degrees).
        lon:         Geographic longitude (decimal degrees).
        ayanamsha:   Ayanamsha system.
        query_time:  Specific time for Hora calculation (defaults to noon UTC).

    Returns:
        PanchangData with all five limbs and supporting data.
    """
    # Use noon UTC for main Panchang computation (standard practice)
    noon_utc = datetime(
        query_date.year, query_date.month, query_date.day, 12, 0, 0,
        tzinfo=timezone.utc,
    )
    jd = compute_julian_day(noon_utc)
    ayanamsha_value = compute_ayanamsha(jd, ayanamsha)

    # Get Sun and Moon positions
    raw_positions = compute_planet_positions(jd, ayanamsha_value)
    sun_lon  = raw_positions[PlanetName.SUN][0]
    moon_lon = raw_positions[PlanetName.MOON][0]

    # Compute five limbs
    tithi      = compute_tithi(sun_lon, moon_lon)
    vara       = compute_vara(query_date)
    nakshatra  = compute_nakshatra_from_moon(moon_lon)
    nithya_yoga = compute_nithya_yoga(sun_lon, moon_lon)
    karana     = compute_karana(sun_lon, moon_lon)

    # Sunrise/sunset
    sunrise, sunset = compute_sunrise_sunset(jd, lat, lon)

    # Hora lord at query time
    hora_lord: Optional[PlanetName] = None
    if sunrise is not None:
        actual_time = query_time or time(12, 0, 0)
        query_dt = datetime(
            query_date.year, query_date.month, query_date.day,
            actual_time.hour, actual_time.minute, actual_time.second,
            tzinfo=timezone.utc,
        )
        hora_lord = compute_hora_lord(query_dt, sunrise, vara)

    return PanchangData(
        panchang_date=query_date,
        lat=lat,
        lon=lon,
        ayanamsha=ayanamsha,
        tithi=tithi,
        vara=vara,
        nakshatra=nakshatra,
        nithya_yoga=nithya_yoga,
        karana=karana,
        sunrise_utc=sunrise,
        sunset_utc=sunset,
        hora_lord=hora_lord,
        sun_longitude=round(sun_lon, 6),
        moon_longitude=round(moon_lon, 6),
    )


def is_auspicious_time(panchang: PanchangData) -> tuple[bool, list[str]]:
    """
    Evaluate overall auspiciousness of a panchang day based on classical rules.

    Returns:
        Tuple of (is_auspicious: bool, reasons: list[str]).
        Reasons list explains what factors contributed to the assessment.
    """
    reasons: list[str] = []
    malefic_count = 0

    # Malefic tithis (Rikta tithis: 4, 9, 14 in each paksha)
    if panchang.tithi.number in (4, 9, 14):
        malefic_count += 1
        reasons.append(f"Rikta tithi ({panchang.tithi.name}) — generally inauspicious")

    # Amavasya and certain Purnima periods
    if panchang.tithi.name in ("Amavasya",):
        malefic_count += 1
        reasons.append("Amavasya — avoided for new ventures")

    # Malefic Nithya Yogas
    if panchang.nithya_yoga.nature == "malefic":
        malefic_count += 1
        reasons.append(f"Malefic Nithya Yoga: {panchang.nithya_yoga.name}")

    # Vishti (Bhadra) Karana — inauspicious
    if panchang.karana.name == "Vishti":
        malefic_count += 1
        reasons.append("Vishti (Bhadra) Karana — inauspicious for new works")

    # Favorable nakshatras for general auspiciousness
    auspicious_nakshatras = {
        "Rohini", "Mrigashira", "Punarvasu", "Pushya", "Hasta", "Chitra",
        "Swati", "Anuradha", "Shravana", "Dhanishtha", "Shatabhisha",
        "Uttara Phalguni", "Uttara Ashadha", "Uttara Bhadrapada",
    }
    if panchang.nakshatra.name in auspicious_nakshatras:
        reasons.append(f"Auspicious nakshatra: {panchang.nakshatra.name}")

    is_auspicious = malefic_count == 0
    return is_auspicious, reasons
