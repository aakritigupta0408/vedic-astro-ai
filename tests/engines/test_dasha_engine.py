"""
test_dasha_engine.py — Unit tests for Vimshottari dasha computation.

Tests cover:
  - VIMSHOTTARI_SEQUENCE integrity (total = 120 years, 9 planets)
  - Nakshatra lord mapping consistency with natal_engine.NAKSHATRA_LORDS
  - Dasha start computation from Moon longitude
  - Maha dasha period boundaries
  - Antar dasha proportions
  - Pratyantar and Sookshma dasha proportions
  - Active dasha window resolution for known dates
  - DashaWindow contains/elapsed helpers
  - Error handling (query_date before birth)
"""

from datetime import date, timedelta

import pytest

from vedic_astro.engines.dasha_engine import (
    DAYS_PER_YEAR,
    VIMSHOTTARI_INDEX,
    VIMSHOTTARI_SEQUENCE,
    VIMSHOTTARI_TOTAL_YEARS,
    VIMSHOTTARI_YEARS,
    compute_antar_dashas,
    compute_maha_dashas,
    compute_pratyantar_dashas,
    compute_sookshma_dashas,
    get_active_dasha_window,
    _get_dasha_start_info,
    _years_to_days,
)
from vedic_astro.engines.natal_engine import (
    NAKSHATRA_LORDS,
    NAKSHATRA_SPAN,
    PlanetName,
)


# ─────────────────────────────────────────────────────────────────────────────
# Sequence integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestVimshottariSequence:
    def test_total_years_is_120(self):
        """All 9 dasha periods must sum to exactly 120 years."""
        total = sum(years for _, years in VIMSHOTTARI_SEQUENCE)
        assert total == pytest.approx(120.0)

    def test_sequence_has_9_planets(self):
        assert len(VIMSHOTTARI_SEQUENCE) == 9

    def test_starts_with_ketu(self):
        assert VIMSHOTTARI_SEQUENCE[0][0] == PlanetName.KETU

    def test_ends_with_mercury(self):
        assert VIMSHOTTARI_SEQUENCE[-1][0] == PlanetName.MERCURY

    def test_no_duplicate_planets(self):
        planets = [p for p, _ in VIMSHOTTARI_SEQUENCE]
        assert len(set(planets)) == 9

    def test_all_navagrahas_present(self):
        """All 9 navagrahas must appear exactly once."""
        expected = {
            PlanetName.KETU, PlanetName.VENUS, PlanetName.SUN, PlanetName.MOON,
            PlanetName.MARS, PlanetName.RAHU, PlanetName.JUPITER,
            PlanetName.SATURN, PlanetName.MERCURY,
        }
        actual = {p for p, _ in VIMSHOTTARI_SEQUENCE}
        assert actual == expected

    def test_known_dasha_years(self):
        """Classical dasha year durations per BPHS."""
        assert VIMSHOTTARI_YEARS[PlanetName.KETU]    == 7.0
        assert VIMSHOTTARI_YEARS[PlanetName.VENUS]   == 20.0
        assert VIMSHOTTARI_YEARS[PlanetName.SUN]     == 6.0
        assert VIMSHOTTARI_YEARS[PlanetName.MOON]    == 10.0
        assert VIMSHOTTARI_YEARS[PlanetName.MARS]    == 7.0
        assert VIMSHOTTARI_YEARS[PlanetName.RAHU]    == 18.0
        assert VIMSHOTTARI_YEARS[PlanetName.JUPITER] == 16.0
        assert VIMSHOTTARI_YEARS[PlanetName.SATURN]  == 19.0
        assert VIMSHOTTARI_YEARS[PlanetName.MERCURY] == 17.0

    def test_vimshottari_index_correct(self):
        assert VIMSHOTTARI_INDEX[PlanetName.KETU]    == 0
        assert VIMSHOTTARI_INDEX[PlanetName.VENUS]   == 1
        assert VIMSHOTTARI_INDEX[PlanetName.MERCURY] == 8

    def test_nakshatra_lords_use_same_sequence(self):
        """NAKSHATRA_LORDS must cycle through the Vimshottari sequence starting at Ketu."""
        sequence_lords = [p for p, _ in VIMSHOTTARI_SEQUENCE]
        for i, lord in enumerate(NAKSHATRA_LORDS):
            expected = sequence_lords[i % 9]
            assert lord == expected, (
                f"NAKSHATRA_LORDS[{i}] = {lord.value}, expected {expected.value}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Dasha start computation
# ─────────────────────────────────────────────────────────────────────────────

class TestDashaStartInfo:
    def test_moon_at_nakshatra_start_full_dasha_remaining(self):
        """
        Moon at exact start of Rohini (nakshatra 3, lord = Moon):
        Elapsed fraction = 0 → full 10 years remaining.
        """
        moon_lon = NAKSHATRA_SPAN * 3  # = 40.0° exactly
        birth_dt = date(2000, 1, 1)
        lord, remaining_years, dasha_start = _get_dasha_start_info(moon_lon, birth_dt)

        assert lord == PlanetName.MOON
        assert remaining_years == pytest.approx(10.0, abs=0.01)
        # If full dasha remaining, start should equal birth date
        assert dasha_start == birth_dt

    def test_moon_at_nakshatra_midpoint_half_dasha_remaining(self):
        """
        Moon at midpoint of Ashwini (nakshatra 0, lord = Ketu, 7 years):
        Elapsed fraction = 0.5 → 3.5 years remaining.
        """
        moon_lon = NAKSHATRA_SPAN * 0.5   # midpoint of Ashwini = 6.667°
        birth_dt = date(2000, 1, 1)
        lord, remaining_years, dasha_start = _get_dasha_start_info(moon_lon, birth_dt)

        assert lord == PlanetName.KETU
        assert remaining_years == pytest.approx(3.5, abs=0.05)
        # Dasha started 3.5 years before birth
        expected_days_before = round(3.5 * DAYS_PER_YEAR)
        assert (birth_dt - dasha_start).days == pytest.approx(expected_days_before, abs=2)

    def test_moon_at_nakshatra_end_minimal_remaining(self):
        """
        Moon near end of Ashwini (99% elapsed, Ketu dasha):
        Remaining years ≈ 0.07 (1% of 7 years).
        """
        moon_lon = NAKSHATRA_SPAN * 0.99
        birth_dt = date(2000, 1, 1)
        lord, remaining_years, _ = _get_dasha_start_info(moon_lon, birth_dt)

        assert lord == PlanetName.KETU
        assert remaining_years == pytest.approx(0.07, abs=0.02)

    def test_different_nakshatras_give_correct_lords(self):
        """Verify lord assignment for 5 different nakshatras."""
        expected = [
            (0 * NAKSHATRA_SPAN + 1.0, PlanetName.KETU),    # Ashwini
            (1 * NAKSHATRA_SPAN + 1.0, PlanetName.VENUS),   # Bharani
            (2 * NAKSHATRA_SPAN + 1.0, PlanetName.SUN),     # Krittika
            (5 * NAKSHATRA_SPAN + 1.0, PlanetName.RAHU),    # Ardra
            (8 * NAKSHATRA_SPAN + 1.0, PlanetName.MERCURY), # Ashlesha
        ]
        for moon_lon, expected_lord in expected:
            lord, _, _ = _get_dasha_start_info(moon_lon, date(2000, 1, 1))
            assert lord == expected_lord, f"Moon at {moon_lon:.2f}° → expected {expected_lord.value}"


# ─────────────────────────────────────────────────────────────────────────────
# Maha dasha periods
# ─────────────────────────────────────────────────────────────────────────────

class TestMahaDashas:
    def test_nine_maha_dashas_computed(self):
        """compute_maha_dashas always returns exactly 9 periods."""
        mahas = compute_maha_dashas(0.0, date(2000, 1, 1))
        assert len(mahas) == 9

    def test_maha_dasha_sequence_order(self):
        """
        Sequence starting from Ashwini (Ketu) must follow Vimshottari order.
        """
        moon_lon = NAKSHATRA_SPAN * 0.0    # Ashwini = Ketu start
        mahas = compute_maha_dashas(moon_lon, date(2000, 1, 1))
        sequence_lords = [p for p, _ in VIMSHOTTARI_SEQUENCE]
        for i, maha in enumerate(mahas):
            assert maha.lord == sequence_lords[i % 9]

    def test_maha_dasha_start_end_contiguous(self):
        """Each Maha dasha must start exactly where the previous ended."""
        mahas = compute_maha_dashas(0.0, date(2000, 1, 1))
        for i in range(1, len(mahas)):
            assert mahas[i].start == mahas[i - 1].end, (
                f"Gap between maha {i-1} and {i}: "
                f"{mahas[i-1].end} → {mahas[i].start}"
            )

    def test_maha_dasha_level_is_1(self):
        """All Mahadasha periods must have level=1."""
        for maha in compute_maha_dashas(0.0, date(2000, 1, 1)):
            assert maha.level == 1

    def test_maha_dasha_total_approx_120_years(self):
        """All 9 periods together should span approximately 120 years."""
        mahas = compute_maha_dashas(0.0, date(2000, 1, 1))
        total_days = sum(m.duration_days for m in mahas)
        total_years = total_days / DAYS_PER_YEAR
        assert total_years == pytest.approx(120.0, abs=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Antar dasha periods
# ─────────────────────────────────────────────────────────────────────────────

class TestAntarDashas:
    def test_nine_antars_per_maha(self):
        mahas = compute_maha_dashas(0.0, date(2000, 1, 1))
        antars = compute_antar_dashas(mahas[0])
        assert len(antars) == 9

    def test_antars_sum_to_maha_duration(self):
        """Sum of antardasha days must equal mahadasha days."""
        mahas = compute_maha_dashas(0.0, date(2000, 1, 1))
        for maha in mahas:
            antars = compute_antar_dashas(maha)
            antar_total = sum(a.duration_days for a in antars)
            maha_total = maha.duration_days
            assert antar_total == pytest.approx(maha_total, abs=2), (
                f"Maha {maha.lord.value}: maha={maha_total}, antars sum={antar_total}"
            )

    def test_antars_contiguous(self):
        """Antardashas within a maha must be contiguous."""
        mahas = compute_maha_dashas(0.0, date(2000, 1, 1))
        antars = compute_antar_dashas(mahas[0])
        for i in range(1, len(antars)):
            assert antars[i].start == antars[i - 1].end

    def test_antars_level_is_2(self):
        mahas = compute_maha_dashas(0.0, date(2000, 1, 1))
        for a in compute_antar_dashas(mahas[0]):
            assert a.level == 2

    def test_antardasha_starts_with_maha_lord(self):
        """First antardasha in any maha must be the maha lord itself."""
        mahas = compute_maha_dashas(0.0, date(2000, 1, 1))
        for maha in mahas:
            antars = compute_antar_dashas(maha)
            assert antars[0].lord == maha.lord

    def test_antar_proportions(self):
        """
        Antar dasha duration = (antar_planet_years / 120) * maha_total_days.
        Verify for first antardasha of Ketu maha.
        """
        mahas = compute_maha_dashas(0.0, date(2000, 1, 1))
        ketu_maha = next(m for m in mahas if m.lord == PlanetName.KETU)
        antars = compute_antar_dashas(ketu_maha)

        # First antardasha = Ketu in Ketu = (7/120) * 7 * 365.25 days
        ketu_antar = antars[0]
        expected_days = round((7.0 / 120.0) * 7.0 * DAYS_PER_YEAR)
        assert ketu_antar.duration_days == pytest.approx(expected_days, abs=2)


# ─────────────────────────────────────────────────────────────────────────────
# Pratyantar dasha periods
# ─────────────────────────────────────────────────────────────────────────────

class TestPratyantar:
    def test_nine_pratyantars_per_antar(self):
        mahas = compute_maha_dashas(0.0, date(2000, 1, 1))
        antars = compute_antar_dashas(mahas[0])
        pratyantars = compute_pratyantar_dashas(antars[0], mahas[0].lord)
        assert len(pratyantars) == 9

    def test_pratyantars_sum_to_antar_duration(self):
        mahas = compute_maha_dashas(0.0, date(2000, 1, 1))
        antars = compute_antar_dashas(mahas[0])
        pratyantars = compute_pratyantar_dashas(antars[0], mahas[0].lord)
        total = sum(p.duration_days for p in pratyantars)
        assert total == pytest.approx(antars[0].duration_days, abs=2)

    def test_pratyantars_contiguous(self):
        mahas = compute_maha_dashas(0.0, date(2000, 1, 1))
        antars = compute_antar_dashas(mahas[0])
        pratyantars = compute_pratyantar_dashas(antars[0], mahas[0].lord)
        for i in range(1, len(pratyantars)):
            assert pratyantars[i].start == pratyantars[i - 1].end

    def test_pratyantars_level_is_3(self):
        mahas = compute_maha_dashas(0.0, date(2000, 1, 1))
        antars = compute_antar_dashas(mahas[0])
        for p in compute_pratyantar_dashas(antars[0], mahas[0].lord):
            assert p.level == 3


# ─────────────────────────────────────────────────────────────────────────────
# Active dasha window
# ─────────────────────────────────────────────────────────────────────────────

class TestActiveDashaWindow:
    def test_window_at_birth_matches_birth_maha(self):
        """Query on birth date must return the active maha at birth."""
        moon_lon = NAKSHATRA_SPAN * 3    # Rohini → Moon maha
        birth_dt = date(2000, 1, 1)
        window = get_active_dasha_window(moon_lon, birth_dt, query_date=birth_dt)

        assert window.mahadasha.lord == PlanetName.MOON
        assert window.antardasha is not None

    def test_window_future_date_advances_maha(self):
        """
        Moon at start of Ashwini (Ketu, 7 years full).
        Query 10 years after birth → must be in Venus maha (20 years, starts after Ketu).
        """
        moon_lon = 0.0   # exact Ashwini start → full Ketu maha ahead
        birth_dt = date(2000, 1, 1)
        # Ketu ends on ~2007-01-01; Venus starts then; 10 years later = 2010 → Venus maha
        query_dt = date(2010, 1, 1)
        window = get_active_dasha_window(moon_lon, birth_dt, query_date=query_dt)

        assert window.mahadasha.lord == PlanetName.VENUS

    def test_window_depth_3_has_pratyantar(self):
        moon_lon = 0.0
        birth_dt = date(2000, 1, 1)
        window = get_active_dasha_window(moon_lon, birth_dt, depth=3)
        assert window.pratyantar is not None

    def test_window_depth_2_no_pratyantar(self):
        moon_lon = 0.0
        birth_dt = date(2000, 1, 1)
        window = get_active_dasha_window(moon_lon, birth_dt, depth=2)
        assert window.pratyantar is None

    def test_window_depth_4_has_sookshma(self):
        moon_lon = 0.0
        birth_dt = date(2000, 1, 1)
        window = get_active_dasha_window(moon_lon, birth_dt, depth=4)
        assert window.sookshma is not None

    def test_query_before_birth_raises(self):
        moon_lon = 0.0
        birth_dt = date(2000, 1, 1)
        with pytest.raises(ValueError, match="before birth_dt"):
            get_active_dasha_window(moon_lon, birth_dt, query_date=date(1999, 1, 1))

    def test_window_maha_contains_query_date(self):
        """The returned mahadasha period must contain the query date."""
        moon_lon = NAKSHATRA_SPAN * 3
        birth_dt = date(2000, 1, 1)
        query_dt = date(2005, 6, 15)
        window = get_active_dasha_window(moon_lon, birth_dt, query_date=query_dt)
        assert window.mahadasha.contains(query_dt)

    def test_window_antar_contains_query_date(self):
        moon_lon = NAKSHATRA_SPAN * 3
        birth_dt = date(2000, 1, 1)
        query_dt = date(2005, 6, 15)
        window = get_active_dasha_window(moon_lon, birth_dt, query_date=query_dt)
        assert window.antardasha.contains(query_dt)


# ─────────────────────────────────────────────────────────────────────────────
# DashaPeriod helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestDashaPeriodHelpers:
    def test_contains_within_range(self):
        from vedic_astro.engines.dasha_engine import DashaPeriod
        period = DashaPeriod(1, PlanetName.MOON, date(2000, 1, 1), date(2010, 1, 1))
        assert period.contains(date(2005, 6, 15))

    def test_contains_at_start_boundary(self):
        from vedic_astro.engines.dasha_engine import DashaPeriod
        period = DashaPeriod(1, PlanetName.MOON, date(2000, 1, 1), date(2010, 1, 1))
        assert period.contains(date(2000, 1, 1))

    def test_not_contains_at_end_boundary(self):
        """End date is exclusive [start, end)."""
        from vedic_astro.engines.dasha_engine import DashaPeriod
        period = DashaPeriod(1, PlanetName.MOON, date(2000, 1, 1), date(2010, 1, 1))
        assert not period.contains(date(2010, 1, 1))

    def test_elapsed_fraction_midpoint(self):
        from vedic_astro.engines.dasha_engine import DashaPeriod
        period = DashaPeriod(1, PlanetName.MOON, date(2000, 1, 1), date(2002, 1, 1))
        mid = date(2001, 1, 1)
        frac = period.elapsed_fraction(mid)
        assert 0.45 < frac < 0.55  # approximately 0.5

    def test_days_remaining_is_positive_before_end(self):
        from vedic_astro.engines.dasha_engine import DashaPeriod
        period = DashaPeriod(1, PlanetName.MOON, date(2000, 1, 1), date(2010, 1, 1))
        assert period.days_remaining(date(2005, 1, 1)) > 0

    def test_duration_days_auto_computed(self):
        from vedic_astro.engines.dasha_engine import DashaPeriod
        period = DashaPeriod(1, PlanetName.MOON, date(2000, 1, 1), date(2001, 1, 1))
        assert period.duration_days == 366  # year 2000 is a leap year
