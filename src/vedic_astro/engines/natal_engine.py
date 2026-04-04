"""
natal_engine.py — Natal chart computation engine.

Pure deterministic math — zero LLM calls.
Computes sidereal planetary positions using Swiss Ephemeris (pyswisseph),
ascendant (lagna), whole-sign house assignments, nakshatra+pada, and dignity.

Caching strategy:
    Cache key  : sha256(dob|tob_utc|lat|lon|ayanamsha)
    TTL        : permanent (natal data is immutable for a given birth moment)
    Invalidate : only on ayanamsha version bump (rotate key prefix) or user
                 correction of birth data (explicit delete by chart_id)
    Hook       : @cache_natal decorator wraps build_natal_chart()

Architecture correction applied:
    - compute_shadbala does NOT take TransitSnapshot (it's purely natal)
    - chart_id is only computed after lat/lon are resolved
    - PlanetName is used consistently (not PlanetBody)
    - Retrograde dignity rule is explicit and configurable
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Any, Callable, Optional

import swisseph as swe

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

NAKSHATRA_SPAN   = 360.0 / 27          # 13.333...°
PADA_SPAN        = NAKSHATRA_SPAN / 4  # 3.333...°
RASHI_SPAN       = 30.0                # degrees per sign
CACHE_KEY_PREFIX = "natal:v1"

NAKSHATRA_NAMES: list[str] = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishtha", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada",
    "Revati",
]

# Vimshottari nakshatra→dasha lord mapping (defined here to avoid circular import with dasha_engine).
# Pattern: every 9 nakshatras cycle through the dasha sequence starting from Ketu.
# Sequence: Ketu, Venus, Sun, Moon, Mars, Rahu, Jupiter, Saturn, Mercury (× 3 = 27)
_VIMSHOTTARI_DASHA_LORDS_ORDERED = None  # populated below after PlanetName is defined

RASHI_NAMES: list[str] = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class AyanamshaType(str, Enum):
    """Supported ayanamsha (sidereal offset) systems."""
    LAHIRI     = "lahiri"
    KP         = "krishnamurti"
    RAMAN      = "raman"
    YUKTESHWAR = "yukteshwar"

    @property
    def swe_id(self) -> int:
        """Swiss Ephemeris constant for this ayanamsha."""
        return {
            AyanamshaType.LAHIRI:     swe.SIDM_LAHIRI,
            AyanamshaType.KP:         swe.SIDM_KRISHNAMURTI,
            AyanamshaType.RAMAN:      swe.SIDM_RAMAN,
            AyanamshaType.YUKTESHWAR: swe.SIDM_YUKTESHWAR,
        }[self]


class PlanetName(str, Enum):
    """Planets used in Parashari Vedic astrology (Navagrahas)."""
    SUN     = "sun"
    MOON    = "moon"
    MARS    = "mars"
    MERCURY = "mercury"
    JUPITER = "jupiter"
    VENUS   = "venus"
    SATURN  = "saturn"
    RAHU    = "rahu"
    KETU    = "ketu"

    @property
    def swe_id(self) -> Optional[int]:
        """Swiss Ephemeris body ID. Ketu is derived from Rahu; returns None."""
        return {
            PlanetName.SUN:     swe.SUN,
            PlanetName.MOON:    swe.MOON,
            PlanetName.MARS:    swe.MARS,
            PlanetName.MERCURY: swe.MERCURY,
            PlanetName.JUPITER: swe.JUPITER,
            PlanetName.VENUS:   swe.VENUS,
            PlanetName.SATURN:  swe.SATURN,
            PlanetName.RAHU:    swe.TRUE_NODE,
            PlanetName.KETU:    None,  # computed as Rahu + 180°
        }.get(self)

    @property
    def is_natural_benefic(self) -> bool:
        return self in (PlanetName.JUPITER, PlanetName.VENUS,
                        PlanetName.MOON, PlanetName.MERCURY)

    @property
    def is_natural_malefic(self) -> bool:
        return self in (PlanetName.SUN, PlanetName.MARS,
                        PlanetName.SATURN, PlanetName.RAHU, PlanetName.KETU)


class Dignity(str, Enum):
    """Planetary dignity (relationship to sign occupied)."""
    EXALTED      = "exalted"
    MOOLATRIKONA = "moolatrikona"
    OWN          = "own"
    FRIEND       = "friend"
    NEUTRAL      = "neutral"
    ENEMY        = "enemy"
    DEBILITATED  = "debilitated"

    @property
    def score(self) -> float:
        """Normalized strength multiplier (classical approximation)."""
        return {
            Dignity.EXALTED:      1.0,
            Dignity.MOOLATRIKONA: 0.85,
            Dignity.OWN:          0.75,
            Dignity.FRIEND:       0.50,
            Dignity.NEUTRAL:      0.35,
            Dignity.ENEMY:        0.20,
            Dignity.DEBILITATED:  0.0,
        }[self]


class RetrogradeDignityRule(str, Enum):
    """
    Classical authority to follow for retrograde dignity adjustment.
    Authorities disagree; this is a configurable choice.
    """
    NONE        = "none"       # No adjustment for retrograde (default safe choice)
    KALIDASA    = "kalidasa"   # Retrograde in debilitation → exalted effect; vice versa
    MANTRESHWAR = "mantreshwar"# Retrograde planets gain full strength regardless of sign

# ─────────────────────────────────────────────────────────────────────────────
# Dignity lookup tables (1-indexed sign numbers, Aries=1)
# ─────────────────────────────────────────────────────────────────────────────

# sign in which planet is exalted
_EXALTATION: dict[PlanetName, int] = {
    PlanetName.SUN:     1,   # Aries
    PlanetName.MOON:    2,   # Taurus
    PlanetName.MARS:    10,  # Capricorn
    PlanetName.MERCURY: 6,   # Virgo
    PlanetName.JUPITER: 4,   # Cancer
    PlanetName.VENUS:   12,  # Pisces
    PlanetName.SATURN:  7,   # Libra
    PlanetName.RAHU:    3,   # Gemini (traditional Parashari)
    PlanetName.KETU:    9,   # Sagittarius (traditional Parashari)
}

# debilitation = 7th from exaltation
_DEBILITATION: dict[PlanetName, int] = {
    p: ((s - 1 + 6) % 12) + 1
    for p, s in _EXALTATION.items()
}

# mooltrikona sign
_MOOLATRIKONA: dict[PlanetName, int] = {
    PlanetName.SUN:     5,   # Leo
    PlanetName.MOON:    2,   # Taurus (0°–3° own, 4°–30° mooltrikona per some; simplified)
    PlanetName.MARS:    1,   # Aries
    PlanetName.MERCURY: 6,   # Virgo
    PlanetName.JUPITER: 9,   # Sagittarius
    PlanetName.VENUS:   7,   # Libra
    PlanetName.SATURN:  11,  # Aquarius
}

# own signs (planet rules these signs) — public for use in yoga/dosha detection
OWN_SIGNS: dict[PlanetName, set[int]] = {
    PlanetName.SUN:     {5},        # Leo
    PlanetName.MOON:    {4},        # Cancer
    PlanetName.MARS:    {1, 8},     # Aries, Scorpio
    PlanetName.MERCURY: {3, 6},     # Gemini, Virgo
    PlanetName.JUPITER: {9, 12},    # Sagittarius, Pisces
    PlanetName.VENUS:   {2, 7},     # Taurus, Libra
    PlanetName.SATURN:  {10, 11},   # Capricorn, Aquarius
    PlanetName.RAHU:    set(),      # Rahu/Ketu don't own signs in Parashari
    PlanetName.KETU:    set(),
}

# Natural friendship table: planet → set of friend planets
_NATURAL_FRIENDS: dict[PlanetName, set[PlanetName]] = {
    PlanetName.SUN:     {PlanetName.MOON, PlanetName.MARS, PlanetName.JUPITER},
    PlanetName.MOON:    {PlanetName.SUN, PlanetName.MERCURY},
    PlanetName.MARS:    {PlanetName.SUN, PlanetName.MOON, PlanetName.JUPITER},
    PlanetName.MERCURY: {PlanetName.SUN, PlanetName.VENUS},
    PlanetName.JUPITER: {PlanetName.SUN, PlanetName.MOON, PlanetName.MARS},
    PlanetName.VENUS:   {PlanetName.MERCURY, PlanetName.SATURN},
    PlanetName.SATURN:  {PlanetName.MERCURY, PlanetName.VENUS},
    PlanetName.RAHU:    {PlanetName.VENUS, PlanetName.SATURN},
    PlanetName.KETU:    {PlanetName.MARS, PlanetName.JUPITER},
}

# Natural enmity table
_NATURAL_ENEMIES: dict[PlanetName, set[PlanetName]] = {
    PlanetName.SUN:     {PlanetName.VENUS, PlanetName.SATURN},
    PlanetName.MOON:    set(),
    PlanetName.MARS:    {PlanetName.MERCURY},
    PlanetName.MERCURY: {PlanetName.MOON},
    PlanetName.JUPITER: {PlanetName.MERCURY, PlanetName.VENUS},
    PlanetName.VENUS:   {PlanetName.SUN, PlanetName.MOON},
    PlanetName.SATURN:  {PlanetName.SUN, PlanetName.MOON, PlanetName.MARS},
    PlanetName.RAHU:    {PlanetName.SUN, PlanetName.MOON},
    PlanetName.KETU:    {PlanetName.VENUS, PlanetName.SATURN},
}

# Sign lords (Aries=1 ... Pisces=12)
# Vimshottari dasha lord sequence (Ketu first per Parashari)
# Defined here (not in dasha_engine) to break the circular import:
#   natal_engine.compute_nakshatra() needs this →
#   dasha_engine.NAKSHATRA_LORDS needs this → imports natal_engine
_DASHA_LORD_SEQ: list[PlanetName] = [
    PlanetName.KETU, PlanetName.VENUS, PlanetName.SUN, PlanetName.MOON,
    PlanetName.MARS, PlanetName.RAHU, PlanetName.JUPITER,
    PlanetName.SATURN, PlanetName.MERCURY,
]

# Public: nakshatra index (0-based, Ashwini=0) → dasha lord
NAKSHATRA_LORDS: list[PlanetName] = [
    _DASHA_LORD_SEQ[i % 9] for i in range(27)
]

# Public: sign lords (Aries=1 … Pisces=12)
SIGN_LORDS: dict[int, PlanetName] = {
    1:  PlanetName.MARS,
    2:  PlanetName.VENUS,
    3:  PlanetName.MERCURY,
    4:  PlanetName.MOON,
    5:  PlanetName.SUN,
    6:  PlanetName.MERCURY,
    7:  PlanetName.VENUS,
    8:  PlanetName.MARS,
    9:  PlanetName.JUPITER,
    10: PlanetName.SATURN,
    11: PlanetName.SATURN,
    12: PlanetName.JUPITER,
}

# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class NakshatraData:
    """Nakshatra placement details for a planetary position."""
    index: int        # 0-based (0=Ashwini … 26=Revati)
    name: str
    lord: PlanetName
    pada: int         # 1–4
    elapsed_degrees: float   # degrees elapsed within this nakshatra
    elapsed_percent: float   # 0–100


@dataclass(frozen=True)
class PlanetPosition:
    """
    Full sidereal position of a graha (planet) in the natal chart.

    All longitudes are sidereal (ayanamsha-corrected).
    """
    planet: PlanetName
    longitude: float          # 0–360 sidereal
    sign_number: int          # 1–12 (Aries=1 … Pisces=12)
    sign_name: str
    degree_in_sign: float     # 0–30
    house: int                # 1–12 (whole-sign from lagna)
    is_retrograde: bool
    speed: float              # degrees/day (negative = retrograde)
    nakshatra: NakshatraData
    dignity: Dignity


@dataclass
class ShadBala:
    """
    Planetary strength — six-fold (Shadbala).
    All values in Rupas (classical unit).
    Purely natal — no transit data required.
    """
    planet: PlanetName
    sthana_bala: float    # positional strength
    dig_bala: float       # directional strength
    kaala_bala: float     # temporal strength
    chesta_bala: float    # motional strength (from birth-time speed)
    naisargika_bala: float# natural/inherent strength
    drik_bala: float      # aspectual strength (from natal aspects)
    total: float = field(init=False)
    ishta_phala: float = 0.0  # beneficial result index
    kashta_phala: float = 0.0 # malefic result index
    is_sufficient: bool = field(init=False)

    # Classical minimum thresholds (rupas) per BPHS
    _MIN_RUPAS: dict[PlanetName, float] = field(
        default_factory=lambda: {
            PlanetName.SUN:     5.0,
            PlanetName.MOON:    6.0,
            PlanetName.MARS:    5.0,
            PlanetName.MERCURY: 7.0,
            PlanetName.JUPITER: 6.5,
            PlanetName.VENUS:   5.5,
            PlanetName.SATURN:  5.0,
            PlanetName.RAHU:    0.0,
            PlanetName.KETU:    0.0,
        },
        repr=False,
    )

    def __post_init__(self) -> None:
        self.total = (
            self.sthana_bala + self.dig_bala + self.kaala_bala
            + self.chesta_bala + self.naisargika_bala + self.drik_bala
        )
        self.is_sufficient = self.total >= self._MIN_RUPAS.get(self.planet, 5.0)


@dataclass
class BhavaData:
    """Bhava (house) data for one house in the chart."""
    house_number: int           # 1–12
    sign_number: int            # 1–12
    sign_name: str
    lord: PlanetName
    occupants: list[PlanetName] = field(default_factory=list)


@dataclass
class NatalChart:
    """
    Complete natal (Rasi / D1) chart.

    The chart_id is the canonical cache key — must only be set after
    lat/lon are resolved by GeoResolver.
    """
    chart_id: str                               # sha256(dob|tob_utc|lat|lon|ayanamsha)
    dob: date
    tob_utc: datetime                           # birth time in UTC
    lat: float
    lon: float
    ayanamsha: AyanamshaType
    ayanamsha_value: float                      # actual offset in degrees
    jd: float                                   # Julian Day (ephemeris time)
    lagna_longitude: float                      # sidereal ascendant longitude
    lagna_sign: int                             # 1–12
    lagna_sign_name: str
    planets: dict[PlanetName, PlanetPosition]
    bhavas: dict[int, BhavaData]                # house_number → BhavaData
    shadbala: Optional[dict[PlanetName, ShadBala]] = None
    computed_at: Optional[datetime] = None

# ─────────────────────────────────────────────────────────────────────────────
# Cache hook (no-op if Redis unavailable)
# ─────────────────────────────────────────────────────────────────────────────

def _make_chart_id(
    dob: date,
    tob_utc: datetime,
    lat: float,
    lon: float,
    ayanamsha: AyanamshaType,
) -> str:
    """
    Deterministic, permanent cache key for a natal chart.
    Input must have resolved lat/lon (not None).
    """
    payload = f"{dob.isoformat()}|{tob_utc.isoformat()}|{lat:.6f}|{lon:.6f}|{ayanamsha.value}"
    return hashlib.sha256(payload.encode()).hexdigest()


def cache_natal(fn: Callable) -> Callable:
    """
    Decorator: check Redis for cached NatalChart before computing.
    Falls through gracefully if Redis is unavailable.
    Usage: applied to build_natal_chart().
    """
    def wrapper(*args: Any, **kwargs: Any) -> NatalChart:
        try:
            import redis  # optional dependency
            from vedic_astro.tools.cache import get_redis
            r = get_redis()
            # Extract cache key from args — positional order matches build_natal_chart signature
            dob, tob_utc, lat, lon = args[0], args[1], args[2], args[3]
            ayanamsha = kwargs.get("ayanamsha", AyanamshaType.LAHIRI)
            chart_id = _make_chart_id(dob, tob_utc, lat, lon, ayanamsha)
            key = f"{CACHE_KEY_PREFIX}:{chart_id}"
            cached = r.get(key)
            if cached:
                return _deserialize_chart(json.loads(cached))
            result = fn(*args, **kwargs)
            r.set(key, json.dumps(_serialize_chart(result)))  # no TTL — permanent
            return result
        except Exception:
            # Redis unavailable or import error — compute directly
            return fn(*args, **kwargs)
    return wrapper


def _serialize_chart(chart: NatalChart) -> dict:
    """Minimal serialization for Redis storage. Full schema uses Pydantic in storage layer."""
    import dataclasses
    return dataclasses.asdict(chart)  # shallow — sufficient for cache round-trip


def _deserialize_chart(data: dict) -> NatalChart:
    """Reconstruct NatalChart from cached dict. Called only on cache hit."""
    # In production this delegates to the Pydantic schema validator.
    # Placeholder for the storage layer to implement.
    raise NotImplementedError("Deserialization must be implemented in storage layer")

# ─────────────────────────────────────────────────────────────────────────────
# Core computation functions
# ─────────────────────────────────────────────────────────────────────────────

def compute_julian_day(dt_utc: datetime) -> float:
    """
    Convert a UTC datetime to Julian Day Number (ephemeris time).

    Args:
        dt_utc: datetime in UTC (must be timezone-aware or explicitly UTC).

    Returns:
        Julian Day as float (used by Swiss Ephemeris).
    """
    # swe.julday expects UT (≈ UTC for modern dates)
    hour_decimal = (
        dt_utc.hour
        + dt_utc.minute / 60.0
        + dt_utc.second / 3600.0
        + dt_utc.microsecond / 3_600_000_000.0
    )
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour_decimal)


def compute_ayanamsha(jd: float, ayanamsha: AyanamshaType) -> float:
    """
    Compute the ayanamsha offset in degrees for a given Julian Day.

    Args:
        jd:        Julian Day.
        ayanamsha: Which ayanamsha system to use.

    Returns:
        Offset in degrees (tropical longitude - sidereal longitude).
    """
    swe.set_sid_mode(ayanamsha.swe_id)
    return swe.get_ayanamsa_ut(jd)


def tropical_to_sidereal(longitude: float, ayanamsha_value: float) -> float:
    """Subtract ayanamsha offset and normalize to [0, 360)."""
    return (longitude - ayanamsha_value) % 360.0


def longitude_to_sign(longitude: float) -> int:
    """Return 1-based sign number (Aries=1) from a 0–360 sidereal longitude."""
    return int(longitude / RASHI_SPAN) + 1


def compute_nakshatra(longitude: float) -> NakshatraData:
    """
    Compute nakshatra, pada, and elapsed position from a sidereal longitude.

    Args:
        longitude: Sidereal longitude (0–360°).

    Returns:
        NakshatraData with index (0-based), name, lord, pada (1–4), elapsed.
    """
    # Map nakshatra index (0–26)
    nakshatra_index = int(longitude / NAKSHATRA_SPAN) % 27
    elapsed_in_nak = longitude % NAKSHATRA_SPAN
    pada = int(elapsed_in_nak / PADA_SPAN) + 1
    elapsed_percent = (elapsed_in_nak / NAKSHATRA_SPAN) * 100.0

    # NAKSHATRA_LORDS is defined in this module (natal_engine) to avoid circular import
    lord = NAKSHATRA_LORDS[nakshatra_index]

    return NakshatraData(
        index=nakshatra_index,
        name=NAKSHATRA_NAMES[nakshatra_index],
        lord=lord,
        pada=min(pada, 4),
        elapsed_degrees=elapsed_in_nak,
        elapsed_percent=round(elapsed_percent, 2),
    )


def compute_dignity(
    planet: PlanetName,
    sign: int,
    is_retrograde: bool = False,
    retrograde_rule: RetrogradeDignityRule = RetrogradeDignityRule.NONE,
) -> Dignity:
    """
    Determine planetary dignity based on sign placement.

    Retrograde adjustment follows the configured classical authority.
    Rahu and Ketu: standard Parashari dignity table applied.

    Args:
        planet:           The graha.
        sign:             1-based sign number (Aries=1 … Pisces=12).
        is_retrograde:    Whether the planet is retrograde.
        retrograde_rule:  Which classical rule to apply for retrograde planets.

    Returns:
        Dignity enum value.
    """
    base_dignity = _compute_base_dignity(planet, sign)

    if not is_retrograde or retrograde_rule == RetrogradeDignityRule.NONE:
        return base_dignity

    if retrograde_rule == RetrogradeDignityRule.MANTRESHWAR:
        # Retrograde grants full strength regardless of dignity
        return Dignity.OWN if base_dignity in (Dignity.ENEMY, Dignity.DEBILITATED) else base_dignity

    if retrograde_rule == RetrogradeDignityRule.KALIDASA:
        # Reversal: debilitated ↔ exalted
        if base_dignity == Dignity.DEBILITATED:
            return Dignity.EXALTED
        if base_dignity == Dignity.EXALTED:
            return Dignity.DEBILITATED

    return base_dignity


def _compute_base_dignity(planet: PlanetName, sign: int) -> Dignity:
    """Inner function: dignity without retrograde adjustment."""
    if sign == _EXALTATION.get(planet):
        return Dignity.EXALTED
    if sign == _DEBILITATION.get(planet):
        return Dignity.DEBILITATED
    if sign == _MOOLATRIKONA.get(planet):
        return Dignity.MOOLATRIKONA
    if sign in OWN_SIGNS.get(planet, set()):
        return Dignity.OWN

    # Determine sign lord and compare with natural friendship table
    sign_lord = SIGN_LORDS[sign]
    friends  = _NATURAL_FRIENDS.get(planet, set())
    enemies  = _NATURAL_ENEMIES.get(planet, set())

    if sign_lord in friends:
        return Dignity.FRIEND
    if sign_lord in enemies:
        return Dignity.ENEMY
    return Dignity.NEUTRAL


def compute_planet_positions(
    jd: float,
    ayanamsha_value: float,
    retrograde_rule: RetrogradeDignityRule = RetrogradeDignityRule.NONE,
) -> dict[PlanetName, tuple[float, float, bool]]:
    """
    Compute sidereal longitudes and speeds for all 9 Navagrahas.

    Args:
        jd:               Julian Day.
        ayanamsha_value:  Ayanamsha offset in degrees.
        retrograde_rule:  Retrograde dignity adjustment rule.

    Returns:
        Dict mapping PlanetName → (sidereal_longitude, speed_deg_per_day, is_retrograde).
    """
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED  # tropical + speed; ayanamsha applied manually
    results: dict[PlanetName, tuple[float, float, bool]] = {}

    for planet in PlanetName:
        if planet == PlanetName.KETU:
            continue  # derived below

        swe_id = planet.swe_id
        if swe_id is None:
            continue

        xx, ret = swe.calc_ut(jd, swe_id, flags)
        # xx[0]=longitude, xx[3]=speed in longitude (deg/day)
        tropical_lon = xx[0]
        speed = xx[3]
        is_retro = speed < 0.0

        sidereal_lon = tropical_to_sidereal(tropical_lon, ayanamsha_value)
        results[planet] = (sidereal_lon, speed, is_retro)

    # Ketu = Rahu + 180°
    rahu_lon, rahu_speed, _ = results[PlanetName.RAHU]
    ketu_lon = (rahu_lon + 180.0) % 360.0
    # Ketu always retrograde (moves opposite to Rahu's direction)
    results[PlanetName.KETU] = (ketu_lon, -rahu_speed, True)

    return results


def compute_ascendant(
    jd: float,
    lat: float,
    lon: float,
    ayanamsha_value: float,
) -> float:
    """
    Compute the sidereal ascendant (Lagna) longitude.

    Uses Swiss Ephemeris house computation then applies ayanamsha correction.

    Args:
        jd:              Julian Day.
        lat:             Geographic latitude (decimal degrees, N positive).
        lon:             Geographic longitude (decimal degrees, E positive).
        ayanamsha_value: Ayanamsha offset in degrees.

    Returns:
        Sidereal ascendant longitude (0–360°).
    """
    # Placidus gives us the Ascendant degree; we apply ayanamsha manually
    cusps, ascmc = swe.houses(jd, lat, lon, b"P")
    tropical_asc = ascmc[0]  # ascmc[0] = Ascendant
    return tropical_to_sidereal(tropical_asc, ayanamsha_value)


def assign_whole_sign_houses(
    lagna_sign: int,
    planet_data: dict[PlanetName, tuple[float, float, bool]],
) -> dict[PlanetName, int]:
    """
    Assign whole-sign house numbers to each planet.

    In the whole-sign system, the sign containing the Lagna is house 1,
    the next sign is house 2, and so on.

    Args:
        lagna_sign:  1-based sign number of the Ascendant (1=Aries).
        planet_data: Dict of PlanetName → (longitude, speed, is_retrograde).

    Returns:
        Dict of PlanetName → house_number (1–12).
    """
    houses: dict[PlanetName, int] = {}
    for planet, (lon, _, _) in planet_data.items():
        planet_sign = longitude_to_sign(lon)
        # House = (planet_sign - lagna_sign) mod 12 + 1
        house = ((planet_sign - lagna_sign) % 12) + 1
        houses[planet] = house
    return houses


def build_bhavas(
    lagna_sign: int,
    planet_houses: dict[PlanetName, int],
) -> dict[int, BhavaData]:
    """
    Build BhavaData for all 12 houses.

    Args:
        lagna_sign:    1-based sign number of Lagna.
        planet_houses: PlanetName → house number mapping.

    Returns:
        Dict of house_number (1–12) → BhavaData.
    """
    bhavas: dict[int, BhavaData] = {}
    for house_num in range(1, 13):
        sign_num = ((lagna_sign - 1 + house_num - 1) % 12) + 1
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
    return bhavas


def compute_chara_karakas(
    planets: dict[PlanetName, PlanetPosition],
) -> dict[str, PlanetName]:
    """
    Compute Jaimini Chara Karakas (Atmakaraka through Darakaraka).

    Chara Karakas are determined by degree within sign (highest degree = Atmakaraka).
    Rahu and Ketu are excluded; the 7 remaining planets are ranked.

    Args:
        planets: Full planet position map from natal chart.

    Returns:
        Dict mapping karaka name → PlanetName.
        Keys: "atmakaraka", "amatyakaraka", "bhratrikaraka", "matrikaraka",
              "putrakaraka", "gnatikaraka", "darakaraka"
    """
    karaka_names = [
        "atmakaraka", "amatyakaraka", "bhratrikaraka", "matrikaraka",
        "putrakaraka", "gnatikaraka", "darakaraka",
    ]
    eligible = [p for p in PlanetName if p not in (PlanetName.RAHU, PlanetName.KETU)]

    # Sort by degree within sign, descending
    sorted_planets = sorted(
        eligible,
        key=lambda p: planets[p].degree_in_sign,
        reverse=True,
    )

    return {
        karaka: planet
        for karaka, planet in zip(karaka_names, sorted_planets[:7])
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main public API
# ─────────────────────────────────────────────────────────────────────────────

@cache_natal
def build_natal_chart(
    dob: date,
    tob_utc: datetime,
    lat: float,
    lon: float,
    ayanamsha: AyanamshaType = AyanamshaType.LAHIRI,
    retrograde_rule: RetrogradeDignityRule = RetrogradeDignityRule.NONE,
    compute_shadbala: bool = False,
) -> NatalChart:
    """
    Build a complete sidereal natal chart.

    This is the primary entry point for chart computation. All sub-computations
    are deterministic; no LLM is called.

    Cache: Result is permanently cached by chart_id = sha256(dob|tob_utc|lat|lon|ayanamsha).
    The cache decorator wraps this function transparently.

    Args:
        dob:             Date of birth.
        tob_utc:         Time of birth in UTC (timezone-aware recommended).
        lat:             Geographic latitude of birthplace.
        lon:             Geographic longitude of birthplace.
        ayanamsha:       Ayanamsha system (default: Lahiri).
        retrograde_rule: Retrograde dignity adjustment rule.
        compute_shadbala:Whether to compute Shadbala (slower; enable on demand).

    Returns:
        NatalChart with all planetary positions, houses, and nakshatra data.

    Raises:
        ValueError: If lat or lon are None (geo must be resolved before calling).
        RuntimeError: If Swiss Ephemeris data files are not found.
    """
    if lat is None or lon is None:
        raise ValueError(
            "lat and lon must be resolved by GeoResolver before calling build_natal_chart(). "
            "chart_id cannot be computed without geographic coordinates."
        )

    jd = compute_julian_day(tob_utc)
    ayanamsha_value = compute_ayanamsha(jd, ayanamsha)
    chart_id = _make_chart_id(dob, tob_utc, lat, lon, ayanamsha)

    # Compute ascendant
    lagna_lon = compute_ascendant(jd, lat, lon, ayanamsha_value)
    lagna_sign = longitude_to_sign(lagna_lon)
    lagna_sign_name = RASHI_NAMES[lagna_sign - 1]

    # Compute all planet raw data
    raw_planet_data = compute_planet_positions(jd, ayanamsha_value, retrograde_rule)

    # Assign houses (whole-sign)
    planet_houses = assign_whole_sign_houses(lagna_sign, raw_planet_data)

    # Build full PlanetPosition objects
    planets: dict[PlanetName, PlanetPosition] = {}
    for planet, (lon_val, speed, is_retro) in raw_planet_data.items():
        sign_num = longitude_to_sign(lon_val)
        deg_in_sign = lon_val % RASHI_SPAN
        nak_data = compute_nakshatra(lon_val)
        dignity = compute_dignity(planet, sign_num, is_retro, retrograde_rule)
        planets[planet] = PlanetPosition(
            planet=planet,
            longitude=round(lon_val, 6),
            sign_number=sign_num,
            sign_name=RASHI_NAMES[sign_num - 1],
            degree_in_sign=round(deg_in_sign, 4),
            house=planet_houses[planet],
            is_retrograde=is_retro,
            speed=round(speed, 6),
            nakshatra=nak_data,
            dignity=dignity,
        )

    # Build bhavas
    bhavas = build_bhavas(lagna_sign, planet_houses)

    shadbala_data: Optional[dict[PlanetName, ShadBala]] = None
    if compute_shadbala:
        shadbala_data = _compute_all_shadbala(planets, jd, lagna_sign)

    return NatalChart(
        chart_id=chart_id,
        dob=dob,
        tob_utc=tob_utc,
        lat=lat,
        lon=lon,
        ayanamsha=ayanamsha,
        ayanamsha_value=round(ayanamsha_value, 6),
        jd=round(jd, 6),
        lagna_longitude=round(lagna_lon, 6),
        lagna_sign=lagna_sign,
        lagna_sign_name=lagna_sign_name,
        planets=planets,
        bhavas=bhavas,
        shadbala=shadbala_data,
        computed_at=datetime.now(timezone.utc),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Shadbala (six-fold strength) — purely natal, no transit data
# ─────────────────────────────────────────────────────────────────────────────

# Natural strength (Naisargika Bala) in Rupas per BPHS
_NAISARGIKA_BALA: dict[PlanetName, float] = {
    PlanetName.SUN:     60.0,
    PlanetName.MOON:    51.4,
    PlanetName.VENUS:   42.8,
    PlanetName.JUPITER: 34.2,
    PlanetName.MERCURY: 25.7,
    PlanetName.MARS:    17.1,
    PlanetName.SATURN:   8.57,
    PlanetName.RAHU:     0.0,
    PlanetName.KETU:     0.0,
}

# Dig Bala (directional strength) — planet's strong house
_DIG_BALA_HOUSE: dict[PlanetName, int] = {
    PlanetName.SUN:     10,  # 10th house
    PlanetName.MARS:    10,
    PlanetName.SATURN:  7,
    PlanetName.MERCURY: 1,
    PlanetName.JUPITER: 1,
    PlanetName.MOON:    4,
    PlanetName.VENUS:   4,
    PlanetName.RAHU:    3,   # conventional assignment
    PlanetName.KETU:    9,
}


def _compute_sthana_bala(planet: PlanetName, position: PlanetPosition) -> float:
    """
    Sthana Bala (positional strength) — simplified version.
    Full computation includes Uchcha, Sapta-vargaja, Ojayugmarasyamsa, Kendra Bala.
    """
    dignity_scores: dict[Dignity, float] = {
        Dignity.EXALTED:      60.0,
        Dignity.MOOLATRIKONA: 45.0,
        Dignity.OWN:          30.0,
        Dignity.FRIEND:       22.5,
        Dignity.NEUTRAL:      15.0,
        Dignity.ENEMY:         7.5,
        Dignity.DEBILITATED:   0.0,
    }
    base = dignity_scores.get(position.dignity, 15.0)

    # Kendra bonus (houses 1, 4, 7, 10 add 60 shashtiamshas = 1 rupa)
    kendra_bonus = 15.0 if position.house in (1, 4, 7, 10) else 0.0
    return base + kendra_bonus


def _compute_dig_bala(planet: PlanetName, house: int) -> float:
    """
    Dig Bala: maximum (60 shashtiamshas) in strong house, minimum in opposite house.
    Linear interpolation based on distance from strong house.
    """
    strong_house = _DIG_BALA_HOUSE.get(planet, 1)
    weak_house = ((strong_house - 1 + 6) % 12) + 1
    # Distance from strong house (circular, 0–6)
    dist_from_strong = min(
        abs(house - strong_house),
        12 - abs(house - strong_house),
    )
    return 60.0 - (dist_from_strong * 10.0)  # 0–60 range


def _compute_naisargika_bala(planet: PlanetName) -> float:
    """Natural/inherent strength — fixed per planet, independent of position."""
    return _NAISARGIKA_BALA.get(planet, 0.0)


def _compute_chesta_bala(planet: PlanetName, speed: float) -> float:
    """
    Chesta Bala: motional strength from birth-time speed.
    Planets moving at mean speed score ~30; faster/retrograde varies.
    Mean speeds (deg/day): Su=0.985, Mo=13.17, Ma=0.524, Me=1.383, Ju=0.083, Ve=1.214, Sa=0.034
    """
    mean_speeds: dict[PlanetName, float] = {
        PlanetName.SUN:     0.9856,
        PlanetName.MOON:    13.1764,
        PlanetName.MARS:    0.5240,
        PlanetName.MERCURY: 1.3831,
        PlanetName.JUPITER: 0.0831,
        PlanetName.VENUS:   1.2141,
        PlanetName.SATURN:  0.0336,
        PlanetName.RAHU:    0.0529,
        PlanetName.KETU:    0.0529,
    }
    mean = mean_speeds.get(planet, 1.0)
    if mean == 0:
        return 30.0
    ratio = abs(speed) / mean  # > 1 = fast, < 1 = slow/retro
    # Retrograde grants Vakra Chesta Bala (full 60)
    if speed < 0:
        return 60.0
    return min(60.0, ratio * 30.0)


def _compute_all_shadbala(
    planets: dict[PlanetName, PlanetPosition],
    jd: float,
    lagna_sign: int,
) -> dict[PlanetName, ShadBala]:
    """
    Compute Shadbala for all planets.

    Note: Kaala Bala and Drik Bala require full implementation per BPHS ch.27.
    This provides structurally complete stubs for Kaala Bala and Drik Bala
    (full implementation in shadbala_engine.py).
    """
    result: dict[PlanetName, ShadBala] = {}
    for planet, pos in planets.items():
        sthana  = _compute_sthana_bala(planet, pos)
        dig     = _compute_dig_bala(planet, pos.house)
        nais    = _compute_naisargika_bala(planet)
        chesta  = _compute_chesta_bala(planet, pos.speed)
        kaala   = 30.0  # TODO: implement full Kaala Bala (temporal strength from JD)
        drik    = 30.0  # TODO: implement full Drik Bala (from natal aspects)

        result[planet] = ShadBala(
            planet=planet,
            sthana_bala=round(sthana, 2),
            dig_bala=round(dig, 2),
            kaala_bala=round(kaala, 2),
            chesta_bala=round(chesta, 2),
            naisargika_bala=round(nais, 2),
            drik_bala=round(drik, 2),
        )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Utility: chart fingerprint (for rule matching cache key — NOT used as raw key)
# ─────────────────────────────────────────────────────────────────────────────

def chart_fingerprint(chart: NatalChart) -> str:
    """
    Compact canonical string encoding key chart features.
    Used as INPUT to sha256 for the rule_match cache key — never as the raw key itself.

    Format: La:<sign>|<planet_code>:<sign>:<house>|...
    Example: La:5|Su:7:3|Mo:2:10|Ma:1:9|...
    """
    parts = [f"La:{chart.lagna_sign}"]
    for planet in PlanetName:
        pos = chart.planets[planet]
        parts.append(f"{planet.value[:2].title()}:{pos.sign_number}:{pos.house}")
    fingerprint_str = "|".join(parts)
    # Return sha256 of fingerprint string — not the raw string
    return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:16]
