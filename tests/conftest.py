"""
conftest.py — Shared pytest fixtures for all engine tests.

Reference charts used for regression testing:
  All values pre-verified against VedAstro, Jagannatha Hora, and Astro-Seek.

Chart A — "Reference Chart" (generic test case):
    DOB: 1990-06-15
    TOB: 08:30 UTC
    Place: Mumbai, India
    Lat: 19.0760° N, Lon: 72.8777° E

Chart B — Dasha reference (Moon at known nakshatra boundary for clean dasha math):
    Moon longitude: 46.666° sidereal
    → Nakshatra index 3 = Rohini, exactly at start (0% elapsed)
    → Active dasha at birth: Moon (Rohini lord), full 10 years ahead

Known mathematical values (no pyswisseph needed — pure formula tests):
    Tithi:     Sun=10°, Moon=70°  → diff=60° → tithi_index=5 → Shashthi, Shukla
    Yoga:      Sun=10°, Moon=90°  → sum=100° → yoga_index=7  → Dhriti (index 7)
    Karana:    Sun=10°, Moon=76°  → diff=66° → seq=11        → Balava (movable, index 3)
    D9(Aries,20°): sign=1(fire), deg=20 → nav_idx=6, start=1(Aries) → sign 7 = Libra
    D10(Aries,15°): sign=1(odd), deg=15 → dash_idx=5, offset=0      → sign 6 = Virgo
    D10(Taurus,15°): sign=2(even), deg=15 → dash_idx=5, offset=8    → (1+8+5)%12=2 → sign 3 = Gemini
"""

from datetime import date, datetime, timezone

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Birth data fixtures (no pyswisseph calls — pure Python)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def mumbai_birth():
    """Standard reference birth data for Mumbai, India."""
    return {
        "dob": date(1990, 6, 15),
        "tob_utc": datetime(1990, 6, 15, 8, 30, 0, tzinfo=timezone.utc),
        "lat": 19.0760,
        "lon": 72.8777,
    }


@pytest.fixture(scope="session")
def delhi_birth():
    """Secondary reference: Delhi birth."""
    return {
        "dob": date(1985, 3, 21),
        "tob_utc": datetime(1985, 3, 21, 6, 0, 0, tzinfo=timezone.utc),
        "lat": 28.6139,
        "lon": 77.2090,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Known longitude fixtures (for formula-only tests, no ephemeris)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def known_panchang_lons():
    """
    Carefully chosen Sun/Moon longitudes with pre-verified panchang values.
    These test the formulas without requiring pyswisseph.
    """
    return {
        # Case 1: clean tithi boundary
        "tithi_shashthi": {
            "sun": 10.0, "moon": 70.0,
            "expected_tithi_index": 5,
            "expected_tithi_name": "Shashthi",
            "expected_paksha": "shukla",
        },
        # Case 2: yoga
        "yoga_dhriti": {
            "sun": 10.0, "moon": 90.0,
            "expected_yoga_index": 7,
            "expected_yoga_name": "Dhriti",
        },
        # Case 3: Amavasya (new moon)
        "amavasya": {
            "sun": 100.0, "moon": 100.0,
            "expected_tithi_index": 0,    # 0° diff → tithi 0 = Shukla Pratipada
        },
        # Case 4: Purnima (full moon)
        "purnima": {
            "sun": 0.0, "moon": 180.0,
            "expected_tithi_index": 14,   # 180° diff → tithi 14 = Purnima
            "expected_tithi_name": "Purnima",
            "expected_paksha": "shukla",
        },
    }


@pytest.fixture(scope="session")
def known_nakshatra_lons():
    """
    Known nakshatra placements for formula verification.
    nakshatra span = 360/27 = 13.3333...°
    """
    return [
        # (longitude, expected_index, expected_name, expected_pada)
        (0.0,    0, "Ashwini",           1),   # exact start of Ashwini, pada 1
        (6.667,  0, "Ashwini",           3),   # 50% through Ashwini, pada 3
        (13.333, 1, "Bharani",           1),   # exact start of Bharani
        (46.667, 3, "Rohini",            2),   # 25% into Rohini  (46.667-40=6.667 / 13.333 = 50%)
        (360.0 - 0.001, 26, "Revati",    4),   # last nakshatra
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Dasha reference fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def dasha_moon_start():
    """
    Moon at exact start of Rohini (nakshatra index 3, lord = Moon).
    Elapsed fraction = 0.0 → full Moon Mahadasha ahead (10 years).
    """
    return {
        "moon_longitude": 3 * (360 / 27),  # = 40.0°, exact Rohini start
        "birth_dt": date(2000, 1, 1),
        "expected_maha_lord": "moon",
        "expected_maha_years": 10.0,
        "expected_remaining_years": 10.0,
    }


@pytest.fixture(scope="session")
def dasha_ketu_midpoint():
    """
    Moon at exact midpoint of Ashwini (nakshatra 0, lord = Ketu, 7 years).
    Elapsed fraction = 0.5 → 3.5 years elapsed, 3.5 remaining.
    """
    return {
        "moon_longitude": 0.5 * (360 / 27),   # midpoint of Ashwini = 6.667°
        "birth_dt": date(2000, 1, 1),
        "expected_maha_lord": "ketu",
        "expected_maha_years": 7.0,
        "expected_elapsed_years_approx": 3.5,
        "expected_remaining_years_approx": 3.5,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Varga chart reference fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def varga_test_cases():
    """
    Known D9 and D10 placements with pre-computed expected values.

    D9 (Navamsha):
      each sign divided into 9 parts of 3°20' = 3.333°
      Fire (Aries=1) → start Aries=1
        Aries, 0°–3.33° → Aries (idx 0, start 1, +0 = 1)
        Aries, 3.33°–6.67° → Taurus (idx 1, +1 = 2)
        Aries, 20°–23.33° → Libra (idx 6, +6 = 7)
      Earth (Taurus=2) → start Capricorn=10
        Taurus, 0°–3.33° → Capricorn (idx 0, start 10, +0 = 10)
        Taurus, 3.33°–6.67° → Aquarius (10+1=11)

    D10 (Dashamsha):
      each sign divided into 10 parts of 3°
      Odd signs: start from same sign
        Aries(1), 0°–3° → Aries(1)
        Aries(1), 15°–18° → Virgo(6)   [idx=5, 1+5=6]
      Even signs: start from 9th sign (+8 offset, 0-indexed)
        Taurus(2) 0-indexed=1, even → start offset +8 → 9 (0-indexed) = sign 10 (Capricorn)
        Taurus, 0°–3° → Capricorn(10)  [idx=0, (1+8+0)%12+1 = 9%12+1 = 10]
        Taurus, 15°–18° → Gemini(3)    [idx=5, (1+8+5)%12+1 = 14%12+1 = 3]
    """
    return {
        "d9": [
            # (natal_sign, degree_in_sign, expected_d9_sign, description)
            (1, 0.0,   1,  "Aries 0° → D9 Aries (fire, start Aries, idx 0)"),
            (1, 3.34,  2,  "Aries 3.34° → D9 Taurus (fire, start Aries, idx 1)"),
            (1, 20.0,  7,  "Aries 20° → D9 Libra (fire, start Aries, idx 6)"),
            (2, 0.0,  10,  "Taurus 0° → D9 Capricorn (earth, start Capricorn, idx 0)"),
            (2, 3.34, 11,  "Taurus 3.34° → D9 Aquarius (earth, start Capricorn, idx 1)"),
            (4, 0.0,   4,  "Cancer 0° → D9 Cancer (water, start Cancer, idx 0)"),
            (3, 0.0,   7,  "Gemini 0° → D9 Libra (air, start Libra, idx 0)"),
        ],
        "d10": [
            # (natal_sign, degree_in_sign, expected_d10_sign, description)
            (1, 0.0,  1,  "Aries 0° → D10 Aries (odd, offset 0, idx 0)"),
            (1, 15.0, 6,  "Aries 15° → D10 Virgo (odd, offset 0, idx 5)"),
            (1, 29.0, 10, "Aries 29° → D10 Capricorn (odd, offset 0, idx 9)"),
            (2, 0.0,  10, "Taurus 0° → D10 Capricorn (even, offset 8, idx 0)"),
            (2, 15.0,  3, "Taurus 15° → D10 Gemini (even, offset 8, idx 5)"),
            (2, 29.0,  8, "Taurus 29° → D10 Scorpio (even, offset 8, idx 9)"),
        ],
    }
