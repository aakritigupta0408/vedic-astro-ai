"""
test_transit_engine.py — Unit tests for transit engine.

Strategy: tests that require pyswisseph are marked @pytest.mark.integration.
Pure-logic tests (gochara table lookups, sade sati, aspect computation)
use synthetic data and run without any ephemeris dependency.
"""

import pytest

from vedic_astro.engines.transit_engine import (
    GOCHARA_FROM_MOON,
    AspectType,
    GocharyaStrength,
    TransitAspect,
    TransitOverlay,
    TransitPosition,
    TransitSnapshot,
    _check_sadesati,
    _house_distance,
    compute_gochara_strength,
    compute_transit_aspects,
)
from vedic_astro.engines.natal_engine import PlanetName


# ─────────────────────────────────────────────────────────────────────────────
# House distance helper
# ─────────────────────────────────────────────────────────────────────────────

class TestHouseDistance:
    @pytest.mark.parametrize("from_sign,to_sign,expected", [
        (1, 1,  1),   # same sign = house 1
        (1, 7,  7),   # 7th from Aries = Libra
        (1, 12, 12),  # 12th from Aries = Pisces
        (7, 1,  7),   # Aries from Libra = 7th
        (12, 1,  2),  # Aries from Pisces = 2nd
        (5, 5,  1),   # same
        (3, 6,  4),   # 4th from Gemini = Virgo (3→4→5→6 = 4 steps)
    ])
    def test_house_distance(self, from_sign, to_sign, expected):
        result = _house_distance(from_sign, to_sign)
        assert result == expected


# ─────────────────────────────────────────────────────────────────────────────
# Gochara strength
# ─────────────────────────────────────────────────────────────────────────────

class TestGocharyaStrength:
    def test_jupiter_in_11th_from_moon_is_favorable(self):
        """Jupiter in 11th from Moon = benefic per classical gochara."""
        # natal Moon in sign 1 (Aries), Jupiter transiting sign 11 (Aquarius)
        r = compute_gochara_strength(PlanetName.JUPITER, 11, 1, 1)
        # house_from_moon = 11 → GOCHARA_FROM_MOON[JUPITER][11] = 1.0
        assert r.strength_from_moon == 1.0
        assert r.is_favorable is True

    def test_saturn_in_1st_from_moon_is_unfavorable(self):
        """Saturn in 1st from natal Moon = unfavorable."""
        r = compute_gochara_strength(PlanetName.SATURN, 1, 1, 1)
        assert r.strength_from_moon == 0.0
        assert r.is_favorable is False

    def test_sun_in_3rd_from_moon_is_favorable(self):
        """Sun in 3rd from natal Moon = favorable (1.0)."""
        # natal Moon sign 1, Sun transiting sign 3
        r = compute_gochara_strength(PlanetName.SUN, 3, 1, 1)
        assert r.strength_from_moon == 1.0

    def test_composite_strength_in_range(self):
        r = compute_gochara_strength(PlanetName.JUPITER, 5, 3, 2)
        assert 0.0 <= r.composite_strength <= 1.0

    def test_gochara_house_computed_correctly(self):
        """With natal Moon in sign 3 and transit in sign 8: house_from_moon = 6."""
        r = compute_gochara_strength(PlanetName.SATURN, 8, 3, 1)
        # house_from_moon = (8-3)%12+1 = 5+1 = 6
        assert r.house_from_moon == 6

    def test_all_9_planets_covered_in_gochara_table(self):
        """All 9 navagrahas must have entries in the gochara table."""
        for planet in PlanetName:
            assert planet in GOCHARA_FROM_MOON, f"{planet.value} missing from GOCHARA_FROM_MOON"

    def test_gochara_table_has_12_houses_per_planet(self):
        """Each planet's gochara table must have entries for all 12 houses."""
        for planet, table in GOCHARA_FROM_MOON.items():
            assert len(table) == 12, f"{planet.value} has {len(table)} entries, expected 12"
            for house in range(1, 13):
                assert house in table, f"{planet.value} missing house {house}"


# ─────────────────────────────────────────────────────────────────────────────
# Sade Sati
# ─────────────────────────────────────────────────────────────────────────────

class TestSadesati:
    def test_sade_sati_rising(self):
        """Saturn in sign before Moon sign = rising phase."""
        natal_moon_sign = 5   # Leo
        saturn_sign = 4       # Cancer (before Leo)
        active, phase = _check_sadesati(saturn_sign, natal_moon_sign)
        assert active is True
        assert phase == "rising"

    def test_sade_sati_peak(self):
        """Saturn in same sign as Moon = peak."""
        natal_moon_sign = 5
        saturn_sign = 5
        active, phase = _check_sadesati(saturn_sign, natal_moon_sign)
        assert active is True
        assert phase == "peak"

    def test_sade_sati_setting(self):
        """Saturn in sign after Moon sign = setting phase."""
        natal_moon_sign = 5
        saturn_sign = 6       # Virgo (after Leo)
        active, phase = _check_sadesati(saturn_sign, natal_moon_sign)
        assert active is True
        assert phase == "setting"

    def test_sade_sati_inactive(self):
        """Saturn far from Moon = no Sade Sati."""
        natal_moon_sign = 5
        saturn_sign = 10      # Capricorn, 5 signs away
        active, phase = _check_sadesati(saturn_sign, natal_moon_sign)
        assert active is False
        assert phase is None

    def test_sade_sati_wraps_at_12(self):
        """Moon in Aries (1), Saturn in Pisces (12) = rising phase (12 is before 1)."""
        natal_moon_sign = 1
        saturn_sign = 12
        active, phase = _check_sadesati(saturn_sign, natal_moon_sign)
        assert active is True
        assert phase == "rising"

    def test_sade_sati_wraps_setting(self):
        """Moon in Pisces (12), Saturn in Aries (1) = setting."""
        natal_moon_sign = 12
        saturn_sign = 1
        active, phase = _check_sadesati(saturn_sign, natal_moon_sign)
        assert active is True
        assert phase == "setting"


# ─────────────────────────────────────────────────────────────────────────────
# Transit aspects
# ─────────────────────────────────────────────────────────────────────────────

class TestTransitAspects:
    def _make_transit_snapshot(self, planet_signs: dict[PlanetName, int]) -> TransitSnapshot:
        """Build a minimal TransitSnapshot mock."""
        from unittest.mock import MagicMock
        from datetime import date

        snapshot = MagicMock(spec=TransitSnapshot)
        snapshot.snapshot_date = date.today()
        positions = {}
        for planet, sign in planet_signs.items():
            pos = MagicMock(spec=TransitPosition)
            pos.sign_number = sign
            pos.speed = 1.0   # direct
            positions[planet] = pos
        for planet in PlanetName:
            if planet not in positions:
                pos = MagicMock(spec=TransitPosition)
                pos.sign_number = 1
                pos.speed = 1.0
                positions[planet] = pos
        snapshot.positions = positions
        return snapshot

    def _make_natal_chart(self, lagna_sign: int, moon_sign: int = 4):
        """Build minimal natal chart mock."""
        from unittest.mock import MagicMock
        from vedic_astro.engines.natal_engine import NatalChart

        chart = MagicMock(spec=NatalChart)
        chart.lagna_sign = lagna_sign

        planets = {}
        for planet in PlanetName:
            pos = MagicMock()
            pos.sign_number = 1
            pos.house = 1
            planets[planet] = pos

        planets[PlanetName.MOON].sign_number = moon_sign
        planets[PlanetName.MOON].house = ((moon_sign - lagna_sign) % 12) + 1

        chart.planets = planets

        bhavas = {}
        for h in range(1, 13):
            bhava = MagicMock()
            bhava.house_number = h
            bhava.occupants = [p for p, pos in planets.items() if pos.house == h]
            bhavas[h] = bhava
        chart.bhavas = bhavas

        return chart

    def test_all_planets_generate_aspects(self):
        """compute_transit_aspects should return aspects from all transiting planets."""
        snapshot = self._make_transit_snapshot(
            {planet: i % 12 + 1 for i, planet in enumerate(PlanetName)}
        )
        natal = self._make_natal_chart(lagna_sign=1)
        aspects = compute_transit_aspects(snapshot, natal)
        # Each planet has at least 1 (7th aspect); some have 3
        assert len(aspects) >= 9  # at least 1 per planet

    def test_seventh_aspect_always_present(self):
        """Every planet should produce at least one FULL aspect (7th drishti)."""
        snapshot = self._make_transit_snapshot({planet: 1 for planet in PlanetName})
        natal = self._make_natal_chart(lagna_sign=1)
        aspects = compute_transit_aspects(snapshot, natal)
        full_aspects = [a for a in aspects if a.aspect_type == AspectType.FULL]
        assert len(full_aspects) >= 9   # one per planet

    def test_mars_generates_special_aspects(self):
        """Mars should generate aspects for houses 4, 7, and 8 from its position."""
        # Mars in house 1 (sign 1, lagna 1)
        snapshot = self._make_transit_snapshot({PlanetName.MARS: 1})
        natal = self._make_natal_chart(lagna_sign=1)
        aspects = compute_transit_aspects(snapshot, natal)
        mars_aspects = [a for a in aspects if a.transit_planet == PlanetName.MARS]
        aspected_houses = {a.aspected_house for a in mars_aspects}
        # Mars in house 1 → 7th (house 7), 4th (house 4), 8th (house 8)
        assert 7 in aspected_houses
        assert 4 in aspected_houses
        assert 8 in aspected_houses

    def test_transit_snapshot_globally_cacheable(self):
        """TransitSnapshot must not contain any chart_id or user-specific field."""
        snapshot = TransitSnapshot.__new__(TransitSnapshot)
        fields = set(snapshot.__dataclass_fields__.keys()) if hasattr(snapshot, '__dataclass_fields__') else set()
        user_specific_fields = {"chart_id", "natal_chart", "aspects_over_natal"}
        overlap = fields & user_specific_fields
        assert len(overlap) == 0, f"TransitSnapshot has user-specific fields: {overlap}"
