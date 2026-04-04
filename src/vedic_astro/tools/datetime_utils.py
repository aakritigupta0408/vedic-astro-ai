"""
datetime_utils.py — Timezone-aware datetime helpers for birth-data handling.

All internal computations use UTC datetimes.  User-facing birth times are
always localised to the birth-place timezone before conversion to UTC.

Usage
-----
    from vedic_astro.tools.datetime_utils import local_to_utc, utc_to_local

    utc_dt = local_to_utc(
        year=1990, month=6, day=15, hour=14, minute=30,
        timezone="Asia/Kolkata"
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def local_to_utc(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int = 0,
    timezone_str: str = "UTC",
) -> datetime:
    """
    Convert a local birth datetime to UTC-aware datetime.

    Parameters
    ----------
    year, month, day, hour, minute, second : Birth date/time components.
    timezone_str : IANA timezone name (e.g. ``"Asia/Kolkata"``).

    Returns
    -------
    datetime
        UTC-aware datetime (tzinfo=UTC).

    Raises
    ------
    ValueError
        If the timezone string is not recognised.
    """
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(timezone_str)
    except (ImportError, zoneinfo.ZoneInfoNotFoundError) as exc:
        raise ValueError(f"Unknown timezone: {timezone_str!r}") from exc

    local_dt = datetime(year, month, day, hour, minute, second, tzinfo=tz)
    return local_dt.astimezone(timezone.utc)


def utc_to_local(utc_dt: datetime, timezone_str: str) -> datetime:
    """
    Convert a UTC datetime to the given local timezone.

    Parameters
    ----------
    utc_dt       : UTC-aware datetime.
    timezone_str : IANA timezone name.

    Returns
    -------
    datetime
        Localised datetime.
    """
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(timezone_str)
    except (ImportError, zoneinfo.ZoneInfoNotFoundError) as exc:
        raise ValueError(f"Unknown timezone: {timezone_str!r}") from exc

    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(tz)


def birth_data_to_utc(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int = 0,
    utc_offset_hours: Optional[float] = None,
    timezone_str: Optional[str] = None,
) -> datetime:
    """
    Flexible birth-data converter that accepts either UTC offset or IANA name.

    Exactly one of *utc_offset_hours* or *timezone_str* must be provided.

    Parameters
    ----------
    utc_offset_hours : e.g. 5.5 for IST, -5.0 for EST.
    timezone_str     : e.g. "Asia/Kolkata".

    Returns
    -------
    datetime (UTC-aware)
    """
    if timezone_str is not None:
        return local_to_utc(year, month, day, hour, minute, second, timezone_str)
    if utc_offset_hours is not None:
        from datetime import timedelta, timezone as _tz
        offset = timedelta(hours=utc_offset_hours)
        fixed_tz = _tz(offset)
        local_dt = datetime(year, month, day, hour, minute, second, tzinfo=fixed_tz)
        return local_dt.astimezone(timezone.utc)
    raise ValueError("Provide either utc_offset_hours or timezone_str.")


def julian_day_to_utc(jd: float) -> datetime:
    """
    Convert a Julian Day Number to a UTC-aware datetime.

    Accurate to within ≈1 second for dates from 1900–2100.
    """
    # JD 2440587.5 = 1970-01-01T00:00:00 UTC
    unix_seconds = (jd - 2440587.5) * 86400.0
    return datetime.fromtimestamp(unix_seconds, tz=timezone.utc)


def utc_to_julian_day(utc_dt: datetime) -> float:
    """Convert a UTC-aware datetime to Julian Day Number."""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    unix_seconds = utc_dt.timestamp()
    return unix_seconds / 86400.0 + 2440587.5
