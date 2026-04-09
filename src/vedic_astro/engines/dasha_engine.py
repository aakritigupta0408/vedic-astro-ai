"""
dasha_engine.py — Vimshottari Dasha computation engine.

Pure deterministic math — zero LLM calls.
Computes the full Vimshottari dasha tree from birth Moon nakshatra,
including Maha, Antar, Pratyantar, and Sookshma dashas. Returns the
active dasha window for any given query date.

Vimshottari system:
    Total cycle: 120 years across 9 planets.
    Sequence: Ketu(7) → Venus(20) → Sun(6) → Moon(10) → Mars(7)
              → Rahu(18) → Jupiter(16) → Saturn(19) → Mercury(17)

Caching strategy:
    Cache key : sha256(dob|tob_utc|lat|lon) — dasha tree is permanent for a birth
    TTL       : permanent (Vimshottari sequence is determined by birth Moon nakshatra)
    Invalidate: only on birth data correction

Architecture note:
    DashaWindow goes to Sookshma depth (4 levels), matching research findings
    that Vimshottari has 6 levels total. Prana and Dehadasha are rarely used
    and are excluded from this engine (V1 scope decision).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from vedic_astro.engines.natal_engine import (
    NakshatraData,
    NatalChart,
    PlanetName,
    NAKSHATRA_LORDS,   # canonical source — defined in natal_engine to avoid circular import
    NAKSHATRA_SPAN,
    get_mutual_relationship,  # re-exported here so dasha callers have one import point
)

# ─────────────────────────────────────────────────────────────────────────────
# Vimshottari constants
# ─────────────────────────────────────────────────────────────────────────────

VIMSHOTTARI_TOTAL_YEARS = 120.0

# Dasha sequence and duration in years (Parashari order starting from Ketu)
VIMSHOTTARI_SEQUENCE: list[tuple[PlanetName, float]] = [
    (PlanetName.KETU,    7.0),
    (PlanetName.VENUS,  20.0),
    (PlanetName.SUN,     6.0),
    (PlanetName.MOON,   10.0),
    (PlanetName.MARS,    7.0),
    (PlanetName.RAHU,   18.0),
    (PlanetName.JUPITER,16.0),
    (PlanetName.SATURN, 19.0),
    (PlanetName.MERCURY,17.0),
]

# Lookup: planet → its Vimshottari dasha duration in years
VIMSHOTTARI_YEARS: dict[PlanetName, float] = dict(VIMSHOTTARI_SEQUENCE)

# Sequence index for each planet (Ketu=0, Venus=1, ... Mercury=8)
VIMSHOTTARI_INDEX: dict[PlanetName, int] = {
    p: i for i, (p, _) in enumerate(VIMSHOTTARI_SEQUENCE)
}

# NAKSHATRA_LORDS imported from natal_engine — see import block above.
# Do NOT redefine here; natal_engine is the canonical source to break circular dependency.

# Days per year (Julian — standard in Jyotish dasha computation)
DAYS_PER_YEAR = 365.25

# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DashaPeriod:
    """
    A single dasha period at any level (Maha, Antar, Pratyantar, Sookshma).

    Children are populated lazily for Sookshma and deeper levels.
    """
    level: int                  # 1=Maha, 2=Antar, 3=Pratyantar, 4=Sookshma
    lord: PlanetName
    start: date
    end: date
    duration_days: int = field(init=False)
    children: list["DashaPeriod"] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.duration_days = (self.end - self.start).days

    def contains(self, query_date: date) -> bool:
        """True if query_date falls within [start, end).

        Half-open interval is intentional: a dasha transitions at the START of
        the end date, so that date belongs to the next period. This matches the
        standard Vimshottari convention used in Jyotish software.
        """
        return self.start <= query_date < self.end

    def elapsed_fraction(self, query_date: date) -> float:
        """Fraction of this period elapsed at query_date (0.0–1.0)."""
        if self.duration_days == 0:
            return 0.0
        elapsed = (query_date - self.start).days
        return min(1.0, max(0.0, elapsed / self.duration_days))

    def days_remaining(self, query_date: date) -> int:
        """Days remaining in this period from query_date."""
        return max(0, (self.end - query_date).days)


@dataclass
class DashaLordStrength:
    """Strength summary of a dasha lord in the natal chart."""
    lord: PlanetName
    house: int
    sign_number: int
    sign_name: str
    is_retrograde: bool
    dignity_name: str
    dignity_score: float    # 0.0–1.0
    is_atmakaraka: bool = False
    is_yogakaraka: bool = False


@dataclass
class DashaWindow:
    """
    Active dasha periods at a specific query date (up to Sookshma level).

    Architecture correction: extended to 4 levels (Maha→Antar→Pratyantar→Sookshma)
    as confirmed by classical texts. Prana and Dehadasha excluded (V1 scope).
    """
    query_date: date
    mahadasha: DashaPeriod
    antardasha: DashaPeriod
    pratyantar: Optional[DashaPeriod] = None
    sookshma: Optional[DashaPeriod] = None
    maha_lord_strength: Optional[DashaLordStrength] = None
    antar_lord_strength: Optional[DashaLordStrength] = None


# ─────────────────────────────────────────────────────────────────────────────
# Core computation
# ─────────────────────────────────────────────────────────────────────────────

def _years_to_days(years: float) -> int:
    """Convert fractional years to whole days (Julian year = 365.25 days)."""
    return round(years * DAYS_PER_YEAR)


def _get_dasha_start_info(
    moon_longitude: float,
    birth_dt: date,
) -> tuple[PlanetName, float, date]:
    """
    Determine the active Mahadasha lord at birth and when it started.

    The Moon's position within its nakshatra determines how much of the
    dasha has already elapsed at the time of birth.

    Args:
        moon_longitude: Sidereal Moon longitude (0–360°).
        birth_dt:       Date of birth.

    Returns:
        Tuple of:
        - active_lord:   The Mahadasha planet active at birth.
        - years_remaining: Years remaining in that dasha at birth.
        - dasha_start:   The date when this Mahadasha started (before birth).
    """
    nakshatra_index = int(moon_longitude / NAKSHATRA_SPAN) % 27
    active_lord = NAKSHATRA_LORDS[nakshatra_index]
    dasha_years = VIMSHOTTARI_YEARS[active_lord]

    # How far into the nakshatra is the Moon?
    elapsed_in_nak = moon_longitude % NAKSHATRA_SPAN
    elapsed_fraction = elapsed_in_nak / NAKSHATRA_SPAN  # 0.0–1.0

    # Elapsed dasha years at birth = fraction * total dasha years
    elapsed_years = elapsed_fraction * dasha_years
    years_remaining = dasha_years - elapsed_years

    # Dasha started 'elapsed_years' before birth
    elapsed_days = _years_to_days(elapsed_years)
    dasha_start = birth_dt - timedelta(days=elapsed_days)

    return active_lord, years_remaining, dasha_start


def _planet_at_index(sequence_start_index: int, offset: int) -> PlanetName:
    """Get the planet at (sequence_start_index + offset) mod 9 in Vimshottari sequence."""
    return VIMSHOTTARI_SEQUENCE[(sequence_start_index + offset) % 9][0]


def compute_maha_dashas(
    moon_longitude: float,
    birth_dt: date,
) -> list[DashaPeriod]:
    """
    Compute all 9 Mahadasha periods (full 120-year cycle) starting from birth.

    The first Mahadasha may start before birth (partially elapsed at birth).

    Args:
        moon_longitude: Sidereal Moon longitude at birth.
        birth_dt:       Date of birth.

    Returns:
        List of 9 DashaPeriod objects (level=1), ordered chronologically.
    """
    active_lord, years_remaining, first_start = _get_dasha_start_info(
        moon_longitude, birth_dt
    )
    start_index = VIMSHOTTARI_INDEX[active_lord]

    maha_dashas: list[DashaPeriod] = []
    current_start = first_start

    for offset in range(9):
        planet = _planet_at_index(start_index, offset)
        years = VIMSHOTTARI_YEARS[planet]

        if offset == 0:
            # First dasha: only the remaining portion from birth
            end = current_start + timedelta(days=_years_to_days(years))
        else:
            end = current_start + timedelta(days=_years_to_days(years))

        maha_dashas.append(DashaPeriod(
            level=1,
            lord=planet,
            start=current_start,
            end=end,
        ))
        current_start = end

    return maha_dashas


def compute_antar_dashas(maha: DashaPeriod) -> list[DashaPeriod]:
    """
    Compute all 9 Antardasha (sub-period) periods within a Mahadasha.

    Antardasha duration formula:
        antar_duration = (maha_duration × antar_planet_years) / 120

    The sequence starts from the Mahadasha lord itself.

    Args:
        maha: The parent Mahadasha period.

    Returns:
        List of 9 DashaPeriod objects (level=2).
    """
    start_index = VIMSHOTTARI_INDEX[maha.lord]
    maha_total_days = _years_to_days(VIMSHOTTARI_YEARS[maha.lord])

    antar_dashas: list[DashaPeriod] = []
    current_start = maha.start

    for offset in range(9):
        planet = _planet_at_index(start_index, offset)
        antar_years = VIMSHOTTARI_YEARS[planet]
        # Proportion of the Mahadasha belonging to this Antardasha
        fraction = antar_years / VIMSHOTTARI_TOTAL_YEARS
        antar_days = round(maha_total_days * fraction)
        end = current_start + timedelta(days=antar_days)

        antar_dashas.append(DashaPeriod(
            level=2,
            lord=planet,
            start=current_start,
            end=end,
        ))
        current_start = end

    # Align last antardasha end to mahadasha end (rounding drift correction)
    if antar_dashas:
        antar_dashas[-1] = DashaPeriod(
            level=2,
            lord=antar_dashas[-1].lord,
            start=antar_dashas[-1].start,
            end=maha.end,
        )

    return antar_dashas


def compute_pratyantar_dashas(antar: DashaPeriod, maha_lord: PlanetName) -> list[DashaPeriod]:
    """
    Compute all 9 Pratyantar dasha (sub-sub-period) periods within an Antardasha.

    Pratyantar duration formula:
        pratyantar_duration = (antar_duration × pratyantar_planet_years) / 120

    The sequence starts from the Antardasha lord.

    Args:
        antar:      The parent Antardasha period.
        maha_lord:  The parent Mahadasha lord (for sequence validation).

    Returns:
        List of 9 DashaPeriod objects (level=3).
    """
    start_index = VIMSHOTTARI_INDEX[antar.lord]
    antar_total_days = (antar.end - antar.start).days

    pratyantars: list[DashaPeriod] = []
    current_start = antar.start

    for offset in range(9):
        planet = _planet_at_index(start_index, offset)
        planet_years = VIMSHOTTARI_YEARS[planet]
        fraction = planet_years / VIMSHOTTARI_TOTAL_YEARS
        pratyantar_days = round(antar_total_days * fraction)
        end = current_start + timedelta(days=pratyantar_days)

        pratyantars.append(DashaPeriod(
            level=3,
            lord=planet,
            start=current_start,
            end=end,
        ))
        current_start = end

    if pratyantars:
        pratyantars[-1] = DashaPeriod(
            level=3,
            lord=pratyantars[-1].lord,
            start=pratyantars[-1].start,
            end=antar.end,
        )

    return pratyantars


def compute_sookshma_dashas(pratyantar: DashaPeriod) -> list[DashaPeriod]:
    """
    Compute all 9 Sookshma dasha (micro-period) periods within a Pratyantar.

    Args:
        pratyantar: The parent Pratyantar period.

    Returns:
        List of 9 DashaPeriod objects (level=4).
    """
    start_index = VIMSHOTTARI_INDEX[pratyantar.lord]
    pratyantar_total_days = (pratyantar.end - pratyantar.start).days

    sookshmas: list[DashaPeriod] = []
    current_start = pratyantar.start

    for offset in range(9):
        planet = _planet_at_index(start_index, offset)
        fraction = VIMSHOTTARI_YEARS[planet] / VIMSHOTTARI_TOTAL_YEARS
        days = round(pratyantar_total_days * fraction)
        end = current_start + timedelta(days=days)

        sookshmas.append(DashaPeriod(
            level=4,
            lord=planet,
            start=current_start,
            end=end,
        ))
        current_start = end

    if sookshmas:
        sookshmas[-1] = DashaPeriod(
            level=4,
            lord=sookshmas[-1].lord,
            start=sookshmas[-1].start,
            end=pratyantar.end,
        )

    return sookshmas


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_active_dasha_window(
    moon_longitude: float,
    birth_dt: date,
    query_date: Optional[date] = None,
    chart: Optional[NatalChart] = None,
    depth: int = 3,
) -> DashaWindow:
    """
    Return the active Vimshottari dasha window at the query date.

    Computes Mahadasha → Antardasha → Pratyantar (→ Sookshma if depth=4)
    for the given query date.

    Cache: The caller (pipeline.py) applies the dasha cache decorator.
    The engine itself is stateless.

    Args:
        moon_longitude: Sidereal Moon longitude at birth (from natal chart).
        birth_dt:       Date of birth (date, not datetime).
        query_date:     Date to find active dashas for. Defaults to today.
        chart:          Optional natal chart (used to extract lord strength data).
        depth:          How many levels to compute: 2=Maha+Antar, 3=+Pratyantar,
                        4=+Sookshma. Higher depth is slower.

    Returns:
        DashaWindow with active periods at all requested levels.

    Raises:
        ValueError: If query_date is before birth_dt.
    """
    if query_date is None:
        from datetime import date as _date
        query_date = _date.today()

    if query_date < birth_dt:
        raise ValueError(
            f"query_date ({query_date}) is before birth_dt ({birth_dt}). "
            "Cannot compute dasha window for a date before birth."
        )

    # Compute all 9 Mahadashas
    mahas = compute_maha_dashas(moon_longitude, birth_dt)

    # Find active Mahadasha
    active_maha = next((m for m in mahas if m.contains(query_date)), None)
    if active_maha is None:
        # query_date beyond 120-year cycle — return last Mahadasha
        active_maha = mahas[-1]

    # Compute Antardashas within active Mahadasha
    antars = compute_antar_dashas(active_maha)
    active_antar = next((a for a in antars if a.contains(query_date)), antars[-1])

    window = DashaWindow(
        query_date=query_date,
        mahadasha=active_maha,
        antardasha=active_antar,
    )

    if depth >= 3:
        pratyantars = compute_pratyantar_dashas(active_antar, active_maha.lord)
        active_pratyantar = next(
            (p for p in pratyantars if p.contains(query_date)), pratyantars[-1]
        )
        window.pratyantar = active_pratyantar

        if depth >= 4:
            sookshmas = compute_sookshma_dashas(active_pratyantar)
            active_sookshma = next(
                (s for s in sookshmas if s.contains(query_date)), sookshmas[-1]
            )
            window.sookshma = active_sookshma

    # Attach lord strength data if natal chart provided
    if chart is not None:
        window.maha_lord_strength = _extract_lord_strength(
            active_maha.lord, chart
        )
        window.antar_lord_strength = _extract_lord_strength(
            active_antar.lord, chart
        )

    return window


def get_upcoming_dasha_windows(
    moon_longitude: float,
    birth_dt: date,
    from_date: Optional[date] = None,
    years_ahead: int = 10,
) -> list[DashaWindow]:
    """
    Get all Antardasha windows for the next N years from from_date.

    Useful for generating a dasha timeline for UI display.

    Args:
        moon_longitude: Sidereal Moon longitude at birth.
        birth_dt:       Date of birth.
        from_date:      Start of forecast window. Defaults to today.
        years_ahead:    How many years ahead to include.

    Returns:
        List of DashaWindows, one per Antardasha period in the forecast window.
    """
    from datetime import date as _date
    if from_date is None:
        from_date = _date.today()

    end_date = from_date + timedelta(days=round(years_ahead * DAYS_PER_YEAR))
    mahas = compute_maha_dashas(moon_longitude, birth_dt)

    windows: list[DashaWindow] = []
    for maha in mahas:
        if maha.end < from_date or maha.start > end_date:
            continue
        antars = compute_antar_dashas(maha)
        for antar in antars:
            if antar.end < from_date or antar.start > end_date:
                continue
            windows.append(DashaWindow(
                query_date=from_date,
                mahadasha=maha,
                antardasha=antar,
            ))

    return windows


def _extract_lord_strength(
    lord: PlanetName,
    chart: NatalChart,
) -> DashaLordStrength:
    """Build DashaLordStrength from a natal chart for a dasha lord planet."""
    pos = chart.planets[lord]
    shadbala = chart.shadbala.get(lord) if chart.shadbala else None

    # Yogakaraka: planet that owns both a kendra and a kona (trine) house
    kendra_lords = {chart.bhavas[h].lord for h in (1, 4, 7, 10)}
    kona_lords   = {chart.bhavas[h].lord for h in (1, 5, 9)}
    is_yogakaraka = lord in (kendra_lords & kona_lords)

    return DashaLordStrength(
        lord=lord,
        house=pos.house,
        sign_number=pos.sign_number,
        sign_name=pos.sign_name,
        is_retrograde=pos.is_retrograde,
        dignity_name=pos.dignity.value,
        dignity_score=pos.dignity.score,
        is_yogakaraka=is_yogakaraka,
        # is_atmakaraka requires compute_chara_karakas — left to pipeline layer
    )
