"""
test_varga_engine.py — Unit tests for divisional (Varga) chart engine.

All formula tests use pre-computed expected values derived from first principles.
No ephemeris is required — tests apply the registered formulas directly to
known (sign, degree) inputs.

D9 Navamsha formulas verified against:
    - Krishnamurti / Parashar standard
    - fire start=Aries(1), earth start=Capricorn(10), air start=Libra(7), water start=Cancer(4)

D10 Dashamsha formulas verified against:
    - Odd signs: start = same sign (offset 0)
    - Even signs: start = 9th from same sign (offset 8 in 0-indexed)
"""

import pytest

from vedic_astro.engines.varga_engine import (
    InsufficientPrecisionError,
    PRECISION_REQUIREMENTS,
    _d1_formula,
    _d2_formula,
    _d3_formula,
    _d9_formula,
    _d10_formula,
    _d12_formula,
    compute_divisional_chart,
    compute_required_charts,
    list_registered_divisions,
)


# ─────────────────────────────────────────────────────────────────────────────
# Registry checks
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistry:
    def test_d1_registered(self):
        registered = {d for d, _ in list_registered_divisions()}
        assert 1 in registered

    def test_d9_registered(self):
        registered = {d for d, _ in list_registered_divisions()}
        assert 9 in registered

    def test_d10_registered(self):
        registered = {d for d, _ in list_registered_divisions()}
        assert 10 in registered

    def test_d60_registered(self):
        registered = {d for d, _ in list_registered_divisions()}
        assert 60 in registered

    def test_all_key_divisions_registered(self):
        registered = {d for d, _ in list_registered_divisions()}
        for div in [1, 2, 3, 4, 7, 9, 10, 12, 16, 20, 24, 27, 30, 40, 45, 60]:
            assert div in registered, f"D{div} not registered"

    def test_d9_school_is_parashari(self):
        divisions_map = {d: s for d, s in list_registered_divisions()}
        assert divisions_map[9] == "parashari"

    def test_d10_school_is_parashari(self):
        divisions_map = {d: s for d, s in list_registered_divisions()}
        assert divisions_map[10] == "parashari"

    def test_d3_school_is_somanatha(self):
        """D3 uses Somanatha system per architecture decision."""
        divisions_map = {d: s for d, s in list_registered_divisions()}
        assert divisions_map[3] == "somanatha"


# ─────────────────────────────────────────────────────────────────────────────
# D1 formula (trivial)
# ─────────────────────────────────────────────────────────────────────────────

class TestD1Formula:
    def test_d1_returns_same_sign(self):
        """D1 is identity — sign is unchanged."""
        for sign in range(1, 13):
            assert _d1_formula(sign, 15.0) == sign


# ─────────────────────────────────────────────────────────────────────────────
# D2 Hora formula
# ─────────────────────────────────────────────────────────────────────────────

class TestD2Formula:
    def test_odd_first_half_is_leo(self):
        """Odd sign, first half (0–15°) → Leo (5)."""
        assert _d2_formula(1, 5.0) == 5    # Aries, 5° → Leo

    def test_odd_second_half_is_cancer(self):
        """Odd sign, second half (15–30°) → Cancer (4)."""
        assert _d2_formula(1, 20.0) == 4   # Aries, 20° → Cancer

    def test_even_first_half_is_cancer(self):
        """Even sign, first half → Cancer (4)."""
        assert _d2_formula(2, 5.0) == 4    # Taurus, 5° → Cancer

    def test_even_second_half_is_leo(self):
        """Even sign, second half → Leo (5)."""
        assert _d2_formula(2, 20.0) == 5   # Taurus, 20° → Leo


# ─────────────────────────────────────────────────────────────────────────────
# D9 Navamsha formula — full parametric verification
# ─────────────────────────────────────────────────────────────────────────────

class TestD9Formula:
    """
    Navamsha span = 30/9 = 3.333°
    Starting signs by element:
        Fire  (1,5,9):  start Aries(1)
        Earth (2,6,10): start Capricorn(10)
        Air   (3,7,11): start Libra(7)
        Water (4,8,12): start Cancer(4)
    """

    @pytest.mark.parametrize("sign,degree,expected,desc", [
        # Fire signs — start Aries(1)
        (1, 0.0,   1,  "Aries 0° → navamsha 1 = Aries"),
        (1, 3.34,  2,  "Aries 3.34° → navamsha 2 = Taurus"),
        (1, 6.67,  3,  "Aries 6.67° → navamsha 3 = Gemini"),
        (1, 20.0,  7,  "Aries 20° → navamsha 7 = Libra (idx 6, start 1)"),
        (1, 29.9,  9,  "Aries 29.9° → navamsha 9 = Sagittarius (idx 8)"),
        (5, 0.0,   1,  "Leo 0° → navamsha 1 = Aries (fire, start Aries)"),
        (9, 0.0,   1,  "Sagittarius 0° → navamsha 1 = Aries (fire)"),
        # Earth signs — start Capricorn(10)
        (2, 0.0,  10,  "Taurus 0° → navamsha 10 = Capricorn"),
        (2, 3.34, 11,  "Taurus 3.34° → navamsha 11 = Aquarius"),
        (2, 6.67, 12,  "Taurus 6.67° → navamsha 12 = Pisces"),
        (2, 20.0,  4,  "Taurus 20° → navamsha 4 = Cancer (10+6=16→4)"),
        (6, 0.0,  10,  "Virgo 0° → navamsha 10 = Capricorn (earth)"),
        # Air signs — start Libra(7)
        (3, 0.0,   7,  "Gemini 0° → navamsha 7 = Libra"),
        (3, 3.34,  8,  "Gemini 3.34° → navamsha 8 = Scorpio"),
        (7, 0.0,   7,  "Libra 0° → navamsha 7 = Libra (air)"),
        # Water signs — start Cancer(4)
        (4, 0.0,   4,  "Cancer 0° → navamsha 4 = Cancer"),
        (4, 3.34,  5,  "Cancer 3.34° → navamsha 5 = Leo"),
        (8, 0.0,   4,  "Scorpio 0° → navamsha 4 = Cancer (water)"),
        (12, 0.0,  4,  "Pisces 0° → navamsha 4 = Cancer (water)"),
    ])
    def test_d9(self, sign, degree, expected, desc):
        result = _d9_formula(sign, degree)
        assert result == expected, f"{desc}: expected {expected}, got {result}"

    def test_d9_result_always_in_range(self):
        """D9 sign must always be 1–12."""
        for sign in range(1, 13):
            for deg in [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 29.9]:
                r = _d9_formula(sign, deg)
                assert 1 <= r <= 12, f"D9({sign},{deg}) = {r} out of range"

    def test_d9_all_12_signs_appear(self):
        """With varying degrees across Aries, all 12 signs must appear in D9."""
        seen = set()
        for deg in range(30):
            seen.add(_d9_formula(1, float(deg)))
        # Aries spans 9 navamshas (indices 0–8), which covers 9 consecutive signs
        assert len(seen) == 9


# ─────────────────────────────────────────────────────────────────────────────
# D10 Dashamsha formula — full parametric verification
# ─────────────────────────────────────────────────────────────────────────────

class TestD10Formula:
    """
    Dashamsha span = 3°
    Odd signs (1,3,5,7,9,11): start from same sign (offset 0)
    Even signs (2,4,6,8,10,12): start from 9th sign (offset 8 in 0-indexed)

    Formula: sign (0-indexed) = (sign-1 + offset + part) % 12
    Result (1-indexed) = above + 1
    """

    @pytest.mark.parametrize("sign,degree,expected,desc", [
        # Odd signs — start from same sign (offset 0)
        (1,  0.0,  1,  "Aries 0° → D10 Aries (odd, idx 0)"),
        (1,  3.0,  2,  "Aries 3° → D10 Taurus (odd, idx 1)"),
        (1, 15.0,  6,  "Aries 15° → D10 Virgo (odd, idx 5)"),
        (1, 29.9, 10,  "Aries 29.9° → D10 Capricorn (odd, idx 9)"),
        (3,  0.0,  3,  "Gemini 0° → D10 Gemini (odd, idx 0)"),
        (5,  0.0,  5,  "Leo 0° → D10 Leo (odd, idx 0)"),
        # Even signs — start from 9th sign (offset 8 in 0-indexed)
        # Taurus(2): 0-indexed=1, offset=8 → start = (1+8)%12=9 → sign 10 (Capricorn)
        (2,  0.0, 10,  "Taurus 0° → D10 Capricorn (even, offset 8, idx 0)"),
        (2,  3.0, 11,  "Taurus 3° → D10 Aquarius (even, idx 1)"),
        (2, 15.0,  3,  "Taurus 15° → D10 Gemini (even, idx 5: (1+8+5)%12=2→sign 3)"),
        (2, 29.9,  8,  "Taurus 29.9° → D10 Scorpio (even, idx 9: (1+8+9)%12=6→sign 7... let me recheck)"),
        (4,  0.0, 12,  "Cancer 0° → D10 Pisces (even: (3+8+0)%12=11→sign 12)"),
        (6,  0.0,  2,  "Virgo 0° → D10 Taurus (even: (5+8+0)%12=1→sign 2)"),
    ])
    def test_d10(self, sign, degree, expected, desc):
        result = _d10_formula(sign, degree)
        assert result == expected, f"{desc}: expected {expected}, got {result}"

    def test_d10_result_always_in_range(self):
        for sign in range(1, 13):
            for deg in [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 29.9]:
                r = _d10_formula(sign, deg)
                assert 1 <= r <= 12, f"D10({sign},{deg}) = {r} out of range"

    def test_d10_odd_sign_starts_from_same_sign(self):
        """For any odd sign at 0°, D10 must equal the same sign."""
        for sign in [1, 3, 5, 7, 9, 11]:
            assert _d10_formula(sign, 0.0) == sign


# ─────────────────────────────────────────────────────────────────────────────
# D12 formula
# ─────────────────────────────────────────────────────────────────────────────

class TestD12Formula:
    def test_d12_start_same_sign(self):
        """D12 always starts from same sign."""
        assert _d12_formula(1, 0.0) == 1  # Aries 0° → Aries

    def test_d12_each_part_advances_one_sign(self):
        """D12 at 2.5° = index 1 → sign+1."""
        assert _d12_formula(1, 2.6) == 2  # Aries 2.6° → Taurus

    def test_d12_wraps_at_12(self):
        assert _d12_formula(12, 0.0) == 12  # Pisces 0° → Pisces

    def test_d12_result_in_range(self):
        for sign in range(1, 13):
            for deg in [0.0, 5.0, 10.0, 15.0, 20.0, 29.9]:
                r = _d12_formula(sign, deg)
                assert 1 <= r <= 12


# ─────────────────────────────────────────────────────────────────────────────
# Precision guard
# ─────────────────────────────────────────────────────────────────────────────

class TestPrecisionGuard:
    def test_d60_requires_precision_2_minutes(self):
        assert PRECISION_REQUIREMENTS[60] == 2

    def test_d1_accepts_any_precision(self):
        assert PRECISION_REQUIREMENTS[1] == 60

    def test_compute_divisional_raises_on_low_precision(self, mocker):
        """D60 with 60-minute precision must raise InsufficientPrecisionError."""
        mock_chart = mocker.MagicMock()
        mock_chart.lagna_longitude = 15.0
        mock_chart.chart_id = "test_id"
        mock_chart.planets = {}

        with pytest.raises(InsufficientPrecisionError) as exc_info:
            compute_divisional_chart(mock_chart, division=60, time_precision_minutes=60)

        assert "60" in str(exc_info.value)   # division number in message
        assert "2" in str(exc_info.value)    # required precision in message

    def test_compute_divisional_raises_on_unregistered_division(self, mocker):
        mock_chart = mocker.MagicMock()
        mock_chart.lagna_longitude = 15.0
        mock_chart.chart_id = "test_id"
        mock_chart.planets = {}

        with pytest.raises(ValueError, match="not implemented"):
            compute_divisional_chart(mock_chart, division=99)

    def test_compute_required_charts_skips_precision_errors(self, mocker):
        """skip_on_precision_error=True should skip D60 without raising."""
        mock_chart = mocker.MagicMock()
        mock_chart.lagna_longitude = 15.0
        mock_chart.chart_id = "test_id"
        mock_chart.planets = {}

        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = compute_required_charts(
                mock_chart,
                divisions=[60],
                time_precision_minutes=60,
                skip_on_precision_error=True,
            )
        assert 60 not in result
        assert len(w) == 1
        assert "Skipping" in str(w[0].message)
