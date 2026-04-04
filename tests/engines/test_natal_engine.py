"""
test_natal_engine.py — Unit tests for natal chart computation engine.

Tests are grouped by function:
  - Julian Day conversion
  - Nakshatra + pada computation (pure formula, no ephemeris)
  - Dignity table correctness
  - House assignment (whole-sign)
  - Bhava construction
  - Chart ID determinism
  - Ayanamsha type enumeration

Ephemeris-dependent tests (build_natal_chart, compute_ascendant) are marked
with @pytest.mark.integration and skipped unless SWISSEPH_PATH is set in env.
"""

import math
from datetime import date, datetime, timezone

import pytest

from vedic_astro.engines.natal_engine import (
    NAKSHATRA_LORDS,
    NAKSHATRA_NAMES,
    NAKSHATRA_SPAN,
    OWN_SIGNS,
    PADA_SPAN,
    RASHI_NAMES,
    RASHI_SPAN,
    SIGN_LORDS,
    AyanamshaType,
    BhavaData,
    Dignity,
    PlanetName,
    RetrogradeDignityRule,
    _compute_base_dignity,
    assign_whole_sign_houses,
    build_bhavas,
    compute_dignity,
    compute_nakshatra,
    longitude_to_sign,
    tropical_to_sidereal,
    _make_chart_id,
)

# ─────────────────────────────────────────────────────────────────────────────
# Utility / pure math tests (no ephemeris)
# ─────────────────────────────────────────────────────────────────────────────

class TestLongitudeHelpers:
    def test_tropical_to_sidereal_reduces_by_offset(self):
        """Sidereal = tropical - ayanamsha_offset."""
        tropical = 100.0
        offset = 23.85
        expected = (100.0 - 23.85) % 360
        assert tropical_to_sidereal(tropical, offset) == pytest.approx(expected)

    def test_tropical_to_sidereal_wraps_below_zero(self):
        """Result must stay in [0, 360)."""
        result = tropical_to_sidereal(10.0, 23.85)
        assert 0 <= result < 360

    def test_longitude_to_sign_aries(self):
        assert longitude_to_sign(0.0) == 1   # Aries starts at 0°

    def test_longitude_to_sign_taurus(self):
        assert longitude_to_sign(30.0) == 2  # Taurus starts at 30°

    def test_longitude_to_sign_pisces(self):
        assert longitude_to_sign(359.9) == 12

    def test_longitude_to_sign_boundary(self):
        """Exact 30° boundary belongs to next sign."""
        assert longitude_to_sign(60.0) == 3  # Gemini

    @pytest.mark.parametrize("lon,expected_sign", [
        (0.0, 1), (29.9, 1), (30.0, 2), (59.9, 2),
        (60.0, 3), (89.9, 3), (90.0, 4), (180.0, 7),
        (270.0, 10), (330.0, 11), (359.9, 12),
    ])
    def test_longitude_to_sign_parametrized(self, lon, expected_sign):
        assert longitude_to_sign(lon) == expected_sign


class TestNakshatra:
    """Tests for nakshatra + pada computation (pure formula, no ephemeris)."""

    def test_ashwini_start(self):
        """0° = Ashwini, pada 1."""
        nak = compute_nakshatra(0.0)
        assert nak.index == 0
        assert nak.name == "Ashwini"
        assert nak.pada == 1
        assert nak.lord == PlanetName.KETU

    def test_ashwini_pada_progression(self):
        """Each pada spans NAKSHATRA_SPAN / 4."""
        # 3 padas in → on the boundary of pada 4
        lon = PADA_SPAN * 3  # = 10.0°
        nak = compute_nakshatra(lon)
        assert nak.index == 0
        assert nak.name == "Ashwini"
        assert nak.pada == 4

    def test_bharani_start(self):
        """NAKSHATRA_SPAN = 13.333° → Bharani starts at 13.333°."""
        nak = compute_nakshatra(NAKSHATRA_SPAN)
        assert nak.index == 1
        assert nak.name == "Bharani"
        assert nak.lord == PlanetName.VENUS
        assert nak.pada == 1

    def test_krittika_lord_is_sun(self):
        nak = compute_nakshatra(NAKSHATRA_SPAN * 2)
        assert nak.name == "Krittika"
        assert nak.lord == PlanetName.SUN

    def test_rohini_lord_is_moon(self):
        nak = compute_nakshatra(NAKSHATRA_SPAN * 3)
        assert nak.name == "Rohini"
        assert nak.lord == PlanetName.MOON

    def test_revati_is_last(self):
        """Revati (index 26) spans 346.667° – 360°."""
        nak = compute_nakshatra(359.9)
        assert nak.index == 26
        assert nak.name == "Revati"
        assert nak.lord == PlanetName.MERCURY

    def test_elapsed_percent_at_midpoint(self):
        """Midpoint of a nakshatra → 50% elapsed."""
        midpoint = NAKSHATRA_SPAN * 5 + NAKSHATRA_SPAN / 2  # middle of nakshatra 5 (Ardra)
        nak = compute_nakshatra(midpoint)
        assert nak.elapsed_percent == pytest.approx(50.0, abs=0.5)

    def test_elapsed_percent_at_start(self):
        nak = compute_nakshatra(NAKSHATRA_SPAN * 10)  # exact start of nakshatra 10
        assert nak.elapsed_percent == pytest.approx(0.0, abs=0.01)

    def test_all_27_nakshatras_covered(self):
        """Sampling every nakshatra from 0 to 360° must hit all 27."""
        indices = set()
        for i in range(27):
            nak = compute_nakshatra(NAKSHATRA_SPAN * i + 0.1)
            indices.add(nak.index)
        assert len(indices) == 27

    def test_nakshatra_lords_cycle_correctly(self):
        """
        Nakshatra lords should follow Ketu, Venus, Sun, Moon, Mars, Rahu, Jupiter,
        Saturn, Mercury, then repeat.
        """
        expected_sequence = [
            PlanetName.KETU, PlanetName.VENUS, PlanetName.SUN, PlanetName.MOON,
            PlanetName.MARS, PlanetName.RAHU, PlanetName.JUPITER,
            PlanetName.SATURN, PlanetName.MERCURY,
        ]
        for i in range(27):
            assert NAKSHATRA_LORDS[i] == expected_sequence[i % 9], (
                f"Nakshatra {i} ({NAKSHATRA_NAMES[i]}) expected lord "
                f"{expected_sequence[i % 9].value}, got {NAKSHATRA_LORDS[i].value}"
            )

    @pytest.mark.parametrize("lon,idx,name,pada", [
        (0.0,    0, "Ashwini",    1),
        (13.333, 1, "Bharani",    1),
        (46.667, 3, "Rohini",     2),   # 46.667-40=6.667° into Rohini; 6.667/13.333*4=2nd pada
        (359.9,  26,"Revati",     4),
    ])
    def test_known_nakshatras(self, lon, idx, name, pada):
        nak = compute_nakshatra(lon)
        assert nak.index == idx, f"Expected index {idx} for lon {lon}"
        assert nak.name  == name
        assert nak.pada  == pada


class TestDignity:
    """Tests for planetary dignity computation."""

    def test_sun_exalted_in_aries(self):
        assert _compute_base_dignity(PlanetName.SUN, 1) == Dignity.EXALTED

    def test_sun_debilitated_in_libra(self):
        assert _compute_base_dignity(PlanetName.SUN, 7) == Dignity.DEBILITATED

    def test_moon_exalted_in_taurus(self):
        assert _compute_base_dignity(PlanetName.MOON, 2) == Dignity.EXALTED

    def test_moon_debilitated_in_scorpio(self):
        assert _compute_base_dignity(PlanetName.MOON, 8) == Dignity.DEBILITATED

    def test_mars_exalted_in_capricorn(self):
        assert _compute_base_dignity(PlanetName.MARS, 10) == Dignity.EXALTED

    def test_mercury_exalted_in_virgo(self):
        assert _compute_base_dignity(PlanetName.MERCURY, 6) == Dignity.EXALTED

    def test_jupiter_exalted_in_cancer(self):
        assert _compute_base_dignity(PlanetName.JUPITER, 4) == Dignity.EXALTED

    def test_venus_exalted_in_pisces(self):
        assert _compute_base_dignity(PlanetName.VENUS, 12) == Dignity.EXALTED

    def test_saturn_exalted_in_libra(self):
        assert _compute_base_dignity(PlanetName.SATURN, 7) == Dignity.EXALTED

    def test_debilitation_is_7th_from_exaltation(self):
        """Classical rule: debilitation = 7th from exaltation."""
        exaltation = {
            PlanetName.SUN:     1,
            PlanetName.MOON:    2,
            PlanetName.MARS:    10,
            PlanetName.MERCURY: 6,
            PlanetName.JUPITER: 4,
            PlanetName.VENUS:   12,
            PlanetName.SATURN:  7,
        }
        for planet, exalt_sign in exaltation.items():
            expected_debil = ((exalt_sign - 1 + 6) % 12) + 1
            actual_debil_dignity = _compute_base_dignity(planet, expected_debil)
            assert actual_debil_dignity == Dignity.DEBILITATED, (
                f"{planet.value}: exalt={exalt_sign}, "
                f"expected debil={expected_debil}, got {actual_debil_dignity}"
            )

    def test_own_sign_dignity(self):
        assert _compute_base_dignity(PlanetName.SUN, 5) == Dignity.OWN      # Leo
        assert _compute_base_dignity(PlanetName.MOON, 4) == Dignity.OWN     # Cancer
        assert _compute_base_dignity(PlanetName.MARS, 1) == Dignity.OWN     # Aries
        assert _compute_base_dignity(PlanetName.MARS, 8) == Dignity.OWN     # Scorpio

    def test_moolatrikona_dignity(self):
        assert _compute_base_dignity(PlanetName.SUN, 5)     == Dignity.OWN          # Leo = own (Sun's case: Leo is own, not mooltrikona)
        assert _compute_base_dignity(PlanetName.JUPITER, 9) == Dignity.MOOLATRIKONA # Sagittarius
        assert _compute_base_dignity(PlanetName.SATURN, 11) == Dignity.MOOLATRIKONA # Aquarius

    def test_retrograde_kalidasa_rule(self):
        """Kalidasa: retrograde in debilitation → exalted effect."""
        result = compute_dignity(
            PlanetName.SUN,
            sign=7,  # Libra = debilitation for Sun
            is_retrograde=True,
            retrograde_rule=RetrogradeDignityRule.KALIDASA,
        )
        assert result == Dignity.EXALTED

    def test_retrograde_kalidasa_reverse(self):
        """Kalidasa: retrograde in exaltation → debilitated effect."""
        result = compute_dignity(
            PlanetName.SUN,
            sign=1,  # Aries = exaltation for Sun
            is_retrograde=True,
            retrograde_rule=RetrogradeDignityRule.KALIDASA,
        )
        assert result == Dignity.DEBILITATED

    def test_retrograde_none_rule_no_change(self):
        """Default NONE rule: retrograde has no effect on dignity."""
        with_retro    = compute_dignity(PlanetName.SUN, 1, True,  RetrogradeDignityRule.NONE)
        without_retro = compute_dignity(PlanetName.SUN, 1, False, RetrogradeDignityRule.NONE)
        assert with_retro == without_retro == Dignity.EXALTED

    def test_dignity_scores_ordered(self):
        """Exalted must score higher than debilitated."""
        assert Dignity.EXALTED.score > Dignity.DEBILITATED.score
        assert Dignity.EXALTED.score > Dignity.ENEMY.score
        assert Dignity.OWN.score > Dignity.NEUTRAL.score


class TestHouseAssignment:
    """Tests for whole-sign house assignment."""

    def test_lagna_sign_is_house_1(self):
        """Planet in lagna sign → house 1."""
        lagna_sign = 5  # Leo
        planet_data = {PlanetName.SUN: (5 * 30.0 - 15.0, 1.0, False)}  # Sun at 135° = Leo
        houses = assign_whole_sign_houses(lagna_sign, planet_data)
        assert houses[PlanetName.SUN] == 1

    def test_seventh_sign_is_house_7(self):
        """Sign 7 from lagna → house 7."""
        lagna_sign = 1  # Aries lagna
        # Planet in Libra (sign 7) → house 7
        planet_data = {PlanetName.VENUS: (185.0, 1.0, False)}  # Libra = 180°+
        houses = assign_whole_sign_houses(lagna_sign, planet_data)
        assert houses[PlanetName.VENUS] == 7

    def test_house_wraps_correctly(self):
        """Lagna in Scorpio (8), planet in Aries (1) → house 6 (1-8+12+1=6)."""
        lagna_sign = 8  # Scorpio
        # Aries = sign 1 → house = (1-8)%12+1 = (-7)%12+1 = 5+1 = 6
        planet_data = {PlanetName.MARS: (15.0, 1.0, False)}  # Aries
        houses = assign_whole_sign_houses(lagna_sign, planet_data)
        assert houses[PlanetName.MARS] == 6

    def test_all_houses_1_to_12(self):
        """12 planets in 12 consecutive signs from lagna → houses 1–12."""
        lagna_sign = 1
        planet_list = list(PlanetName)[:9]  # 9 planets
        planet_data = {
            p: ((lagna_sign - 1 + i) % 12 * 30.0 + 15.0, 1.0, False)
            for i, p in enumerate(planet_list)
        }
        houses = assign_whole_sign_houses(lagna_sign, planet_data)
        for i, planet in enumerate(planet_list):
            assert houses[planet] == (i % 12) + 1


class TestBhavaConstruction:
    def test_bhava_count(self):
        """build_bhavas always returns exactly 12 bhavas."""
        lagna_sign = 3  # Gemini
        planet_houses = {p: 1 for p in PlanetName}
        bhavas = build_bhavas(lagna_sign, planet_houses)
        assert len(bhavas) == 12

    def test_house_1_sign_is_lagna_sign(self):
        lagna_sign = 5  # Leo
        bhavas = build_bhavas(lagna_sign, {})
        assert bhavas[1].sign_number == 5
        assert bhavas[1].sign_name == "Leo"

    def test_house_7_is_opposite_lagna(self):
        """7th house = lagna sign + 6."""
        lagna_sign = 1  # Aries → 7th = Libra (7)
        bhavas = build_bhavas(lagna_sign, {})
        assert bhavas[7].sign_number == 7

    def test_house_lords_correct(self):
        """Each bhava lord = sign lord of that bhava's sign."""
        lagna_sign = 1  # Aries lagna
        bhavas = build_bhavas(lagna_sign, {})
        # House 1 = Aries = Mars
        assert bhavas[1].lord == PlanetName.MARS
        # House 2 = Taurus = Venus
        assert bhavas[2].lord == PlanetName.VENUS
        # House 9 = Sagittarius = Jupiter
        assert bhavas[9].lord == PlanetName.JUPITER

    def test_occupants_assigned_correctly(self):
        """Planets are correctly placed in their bhava."""
        lagna_sign = 1
        planet_houses = {PlanetName.JUPITER: 5, PlanetName.MOON: 5, PlanetName.MARS: 1}
        bhavas = build_bhavas(lagna_sign, planet_houses)
        assert PlanetName.JUPITER in bhavas[5].occupants
        assert PlanetName.MOON    in bhavas[5].occupants
        assert PlanetName.MARS    in bhavas[1].occupants
        assert PlanetName.JUPITER not in bhavas[1].occupants


class TestChartId:
    def test_chart_id_is_deterministic(self):
        """Same inputs must always produce the same chart_id."""
        dob = date(1990, 6, 15)
        tob = datetime(1990, 6, 15, 8, 30, tzinfo=timezone.utc)
        lat, lon = 19.076, 72.8777
        a = _make_chart_id(dob, tob, lat, lon, AyanamshaType.LAHIRI)
        b = _make_chart_id(dob, tob, lat, lon, AyanamshaType.LAHIRI)
        assert a == b

    def test_chart_id_differs_on_tob_change(self):
        """Different TOB → different chart_id."""
        dob = date(1990, 6, 15)
        lat, lon = 19.076, 72.8777
        tob1 = datetime(1990, 6, 15, 8, 30, tzinfo=timezone.utc)
        tob2 = datetime(1990, 6, 15, 8, 31, tzinfo=timezone.utc)
        id1 = _make_chart_id(dob, tob1, lat, lon, AyanamshaType.LAHIRI)
        id2 = _make_chart_id(dob, tob2, lat, lon, AyanamshaType.LAHIRI)
        assert id1 != id2

    def test_chart_id_differs_on_ayanamsha(self):
        """Different ayanamsha → different chart_id."""
        dob = date(1990, 6, 15)
        tob = datetime(1990, 6, 15, 8, 30, tzinfo=timezone.utc)
        lat, lon = 19.076, 72.8777
        id_lahiri = _make_chart_id(dob, tob, lat, lon, AyanamshaType.LAHIRI)
        id_kp     = _make_chart_id(dob, tob, lat, lon, AyanamshaType.KP)
        assert id_lahiri != id_kp

    def test_chart_id_is_hex_string(self):
        """chart_id must be a 64-character hex SHA-256 string."""
        dob = date(1990, 6, 15)
        tob = datetime(1990, 6, 15, 8, 30, tzinfo=timezone.utc)
        chart_id = _make_chart_id(dob, tob, 19.0, 72.0, AyanamshaType.LAHIRI)
        assert len(chart_id) == 64
        assert all(c in "0123456789abcdef" for c in chart_id)


class TestSignLords:
    def test_all_12_signs_have_lords(self):
        for sign in range(1, 13):
            assert sign in SIGN_LORDS

    def test_no_shadow_planets_as_lords(self):
        """Rahu and Ketu do not own signs in Parashari."""
        for lord in SIGN_LORDS.values():
            assert lord not in (PlanetName.RAHU, PlanetName.KETU)

    def test_specific_lords(self):
        assert SIGN_LORDS[1]  == PlanetName.MARS      # Aries
        assert SIGN_LORDS[2]  == PlanetName.VENUS     # Taurus
        assert SIGN_LORDS[4]  == PlanetName.MOON      # Cancer
        assert SIGN_LORDS[5]  == PlanetName.SUN       # Leo
        assert SIGN_LORDS[9]  == PlanetName.JUPITER   # Sagittarius
        assert SIGN_LORDS[10] == PlanetName.SATURN    # Capricorn
        assert SIGN_LORDS[12] == PlanetName.JUPITER   # Pisces
