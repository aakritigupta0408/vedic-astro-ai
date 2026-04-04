"""
hasher.py — Deterministic cache-key generators.

All keys are namespaced under a top-level prefix so every Redis key
can be scanned / flushed by namespace without affecting unrelated data.

Key design rules
----------------
1. Natal chart  → permanent, keyed by birth-data fingerprint (never by name).
2. Transit      → global (no natal data), keyed by date + ayanamsha.
3. Panchang     → keyed by date + location (lat/lon rounded to 0.5°).
4. Overlay      → user-specific, keyed by chart_id + date.
5. LLM response → keyed by sha256(prompt) so identical questions hit cache.

All lat/lon values are rounded to 4 decimal places before hashing so
minor GPS drift across requests does not generate duplicate cache entries.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any


_NS = "va"  # top-level namespace prefix  →  va:natal:<fingerprint>


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sha256_short(data: str, length: int = 16) -> str:
    """Return the first *length* hex characters of sha256(data)."""
    return hashlib.sha256(data.encode()).hexdigest()[:length]


def _round_coord(value: float, decimals: int = 4) -> float:
    """Round a coordinate to *decimals* decimal places."""
    return round(value, decimals)


# ─────────────────────────────────────────────────────────────────────────────
# Public key builders
# ─────────────────────────────────────────────────────────────────────────────

def make_natal_key(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    lat: float,
    lon: float,
    ayanamsha: str = "lahiri",
) -> str:
    """
    Stable, permanent cache key for a natal chart.

    The key is deterministic: the same birth data always maps to the same key.
    Latitude / longitude are rounded to 4 decimals (≈11 m precision), which is
    more than sufficient for house cusp accuracy.

    Returns
    -------
    str
        E.g. ``va:natal:3f2a1b4c8e9d0a12``
    """
    payload = json.dumps(
        {
            "y": year,
            "mo": month,
            "d": day,
            "h": hour,
            "mi": minute,
            "lat": _round_coord(lat),
            "lon": _round_coord(lon),
            "aya": ayanamsha.lower(),
        },
        sort_keys=True,
    )
    return f"{_NS}:natal:{_sha256_short(payload)}"


def make_transit_key(
    snapshot_date: date,
    ayanamsha: str = "lahiri",
) -> str:
    """
    Global transit snapshot key — shared across all users.

    Transit positions for a given calendar date are the same for everyone,
    so the key must contain NO natal-chart data.

    Returns
    -------
    str
        E.g. ``va:transit:2024-06-21:lahiri``
    """
    return f"{_NS}:transit:{snapshot_date.isoformat()}:{ayanamsha.lower()}"


def make_overlay_key(
    chart_id: str,
    overlay_date: date,
) -> str:
    """
    User-specific transit overlay key.

    Combines a globally cached TransitSnapshot with a user's natal chart to
    produce gochara strengths and sade-sati data.  Keyed by (chart_id, date).

    Returns
    -------
    str
        E.g. ``va:overlay:3f2a1b4c8e9d0a12:2024-06-21``
    """
    return f"{_NS}:overlay:{chart_id}:{overlay_date.isoformat()}"


def make_panchang_key(
    panchang_date: date,
    lat: float,
    lon: float,
    ayanamsha: str = "lahiri",
) -> str:
    """
    Panchang cache key — varies by date and geographic location.

    Latitude / longitude rounded to 0.5° (≈55 km) so nearby locations share
    the same Panchang entry.  Vara (weekday) and tithi only change at the
    sunrise/sunset boundary, not by fraction of a degree.

    Returns
    -------
    str
        E.g. ``va:panchang:2024-06-21:19.0:72.5:lahiri``
    """
    lat_r = round(lat * 2) / 2   # nearest 0.5°
    lon_r = round(lon * 2) / 2
    return (
        f"{_NS}:panchang:{panchang_date.isoformat()}"
        f":{lat_r:.1f}:{lon_r:.1f}:{ayanamsha.lower()}"
    )


def make_llm_key(prompt: str) -> str:
    """
    Cache key for LLM narrative responses.

    A sha256 of the full prompt text so identical queries (same planets, same
    question) do not cost an API call.

    Returns
    -------
    str
        E.g. ``va:llm:3f2a1b4c8e9d0a12``
    """
    return f"{_NS}:llm:{_sha256_short(prompt, length=32)}"


def make_geo_key(query: str) -> str:
    """
    Cache key for geocoding results.

    Query is lowercased and stripped before hashing to collapse minor
    whitespace differences.

    Returns
    -------
    str
        E.g. ``va:geo:3f2a1b4c8e9d0a12``
    """
    normalised = query.strip().lower()
    return f"{_NS}:geo:{_sha256_short(normalised)}"
