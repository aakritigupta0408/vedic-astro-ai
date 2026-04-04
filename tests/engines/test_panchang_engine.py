"""
test_panchang_engine.py — Unit tests for Panchang computation engine.

All tests below use known Sun/Moon longitude pairs with pre-verified values.
No pyswisseph calls are made in these formula tests — pure arithmetic is verified.

Pre-verified values:
  Tithi: (moon - sun) / 12° floored → tithi index
  Yoga:  (sun + moon) % 360 / 13.333° floored → yoga index
  Karana: (moon - sun) % 360 / 6° floored → karana sequence number
  Vara:   weekday from date object
"""

from datetime import date

import pytest

from vedic_astro.engines.panchang_engine import (
    KARANA_SPAN,
    MOVABLE_KARANA_NAMES,
    NITHYA_YOGA_NAMES,
    NITHYA_YOGA_SPAN,
    TITHI_NAMES,
    TITHI_SPAN,
    Karana,
    NithyaYoga,
    Tithi,
    Vara,
    compute_karana,
    compute_nithya_yoga,
    compute_tithi,
    compute_vara,
    is_auspicious_time,
)
from vedic_astro.engines.natal_engine import PlanetName


# ─────────────────────────────────────────────────────────────────────────────
# Constants sanity
# ─────────────────────────────────────────────────────────────────────────────

class TestPanchangConstants:
    def test_30_tithi_names(self):
        assert len(TITHI_NAMES) == 30

    def test_27_nithya_yoga_names(self):
        assert len(NITHYA_YOGA_NAMES) == 27

    def test_tithi_span_is_12(self):
        assert TITHI_SPAN == 12.0

    def test_karana_span_is_6(self):
        assert KARANA_SPAN == 6.0

    def test_nithya_yoga_span(self):
        """360 / 27 = 13.333..."""
        assert NITHYA_YOGA_SPAN == pytest.approx(360.0 / 27, abs=1e-6)

    def test_7_movable_karanas(self):
        assert len(MOVABLE_KARANA_NAMES) == 7

    def test_movable_karanas_include_vishti(self):
        """Vishti (Bhadra) is the 7th movable karana."""
        assert "Vishti" in MOVABLE_KARANA_NAMES
        assert MOVABLE_KARANA_NAMES[6] == "Vishti"


# ─────────────────────────────────────────────────────────────────────────────
# Tithi tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTithi:
    @pytest.mark.parametrize("sun,moon,expected_index,expected_name,expected_paksha", [
        (0.0,   0.0,  0,  "Pratipada", "shukla"),    # 0° diff → Shukla Pratipada
        (0.0,  12.0,  1,  "Dvitiya",   "shukla"),    # 12° diff → Shukla Dvitiya
        (0.0,  60.0,  5,  "Shashthi",  "shukla"),    # 60° diff → Shukla Shashthi
        (0.0, 180.0, 15,  "Pratipada", "krishna"),   # 180° diff → Krishna Pratipada (index 15)
        (0.0, 168.0, 14,  "Purnima",   "shukla"),    # 168° diff → Shukla Chaturdashi... wait
        (0.0, 170.0, 14,  "Purnima",   "shukla"),    # 170° / 12 = 14.16 → index 14 = Purnima
        (0.0, 354.0, 29,  "Amavasya",  "krishna"),   # last tithi
    ])
    def test_tithi_formula(self, sun, moon, expected_index, expected_name, expected_paksha):
        t = compute_tithi(sun, moon)
        assert t.index == expected_index, f"sun={sun}, moon={moon}: expected index {expected_index}, got {t.index}"
        assert t.name == expected_name
        assert t.paksha == expected_paksha

    def test_tithi_purnima_is_index_14(self):
        """Purnima = 15th tithi = index 14 (0-based)."""
        t = compute_tithi(0.0, 170.0)   # 170/12 = 14.16 → 14
        assert t.index == 14
        assert t.name == "Purnima"
        assert t.paksha == "shukla"

    def test_tithi_amavasya_is_index_29(self):
        t = compute_tithi(0.0, 354.0)   # 354/12 = 29.5 → index 29
        assert t.index == 29
        assert t.name == "Amavasya"
        assert t.paksha == "krishna"

    def test_tithi_elapsed_at_start(self):
        """At start of a tithi, elapsed_degrees ≈ 0."""
        t = compute_tithi(0.0, 24.0)   # 24/12 = 2.0 exactly → index 2, 0° elapsed
        assert t.elapsed_degrees == pytest.approx(0.0, abs=0.001)

    def test_tithi_elapsed_at_midpoint(self):
        """6° into a tithi = 50% elapsed."""
        t = compute_tithi(0.0, 6.0)    # 6° diff → index 0, 6° elapsed = 50%
        assert t.elapsed_degrees == pytest.approx(6.0, abs=0.001)
        assert t.elapsed_percent == pytest.approx(50.0, abs=0.1)

    def test_tithi_wraps_360(self):
        """Moon behind Sun (e.g., moon=5, sun=355) → diff = 10° → tithi 0."""
        t = compute_tithi(355.0, 5.0)
        assert t.index == 0   # (5 - 355) % 360 = 10° → floor(10/12) = 0

    def test_shukla_tithis_are_1_to_15(self):
        """Indices 0–14 are Shukla paksha."""
        for i in range(15):
            sun = 0.0
            moon = i * 12.0 + 1.0   # 1° into each tithi
            t = compute_tithi(sun, moon)
            assert t.paksha == "shukla", f"Tithi index {t.index} should be shukla"

    def test_krishna_tithis_are_16_to_30(self):
        """Indices 15–29 are Krishna paksha."""
        for i in range(15, 30):
            sun = 0.0
            moon = i * 12.0 + 1.0
            t = compute_tithi(sun, moon)
            assert t.paksha == "krishna", f"Tithi index {t.index} should be krishna"


# ─────────────────────────────────────────────────────────────────────────────
# Vara (weekday) tests
# ─────────────────────────────────────────────────────────────────────────────

class TestVara:
    def test_known_sunday(self):
        """2024-01-07 was a Sunday."""
        v = compute_vara(date(2024, 1, 7))
        assert v.english == "Sunday"
        assert v.lord == PlanetName.SUN
        assert v.weekday_index == 0

    def test_known_monday(self):
        """2024-01-08 was a Monday."""
        v = compute_vara(date(2024, 1, 8))
        assert v.english == "Monday"
        assert v.lord == PlanetName.MOON
        assert v.weekday_index == 1

    def test_known_saturday(self):
        """2024-01-06 was a Saturday."""
        v = compute_vara(date(2024, 1, 6))
        assert v.english == "Saturday"
        assert v.lord == PlanetName.SATURN
        assert v.weekday_index == 6

    def test_vara_lord_sequence(self):
        """Check all 7 weekday lords in sequence."""
        expected_lords = [
            PlanetName.SUN, PlanetName.MOON, PlanetName.MARS, PlanetName.MERCURY,
            PlanetName.JUPITER, PlanetName.VENUS, PlanetName.SATURN,
        ]
        # 2024-01-07 is Sunday (weekday_index 0)
        for offset, expected_lord in enumerate(expected_lords):
            v = compute_vara(date(2024, 1, 7 + offset))
            assert v.lord == expected_lord, (
                f"Day offset {offset}: expected {expected_lord.value}, got {v.lord.value}"
            )

    def test_vara_name_matches_lord(self):
        """Ravivara = Sun, Somavara = Moon, etc."""
        v = compute_vara(date(2024, 1, 7))  # Sunday
        assert "Ravi" in v.name   # Ravivara


# ─────────────────────────────────────────────────────────────────────────────
# Nithya Yoga tests (renamed from 'Yoga' to prevent naming collision)
# ─────────────────────────────────────────────────────────────────────────────

class TestNithyaYoga:
    def test_first_yoga_vishkambha(self):
        """Combined 0° → Vishkambha (index 0)."""
        y = compute_nithya_yoga(0.0, 0.0)   # sum = 0°
        assert y.index == 0
        assert y.name == "Vishkambha"

    def test_yoga_index_formula(self):
        """(sun + moon) % 360 / (360/27) = yoga index."""
        sun, moon = 10.0, 90.0
        combined = (sun + moon) % 360.0
        expected_idx = int(combined / NITHYA_YOGA_SPAN)
        y = compute_nithya_yoga(sun, moon)
        assert y.index == expected_idx

    def test_yoga_wraps_at_360(self):
        """sum > 360 wraps correctly."""
        y = compute_nithya_yoga(300.0, 300.0)   # sum = 600 → 600 % 360 = 240
        expected_idx = int(240.0 / NITHYA_YOGA_SPAN)
        assert y.index == expected_idx

    def test_all_27_yogas_reachable(self):
        """All 27 Nithya Yogas must be reachable by varying longitude."""
        seen = set()
        for i in range(27):
            lon = NITHYA_YOGA_SPAN * i + 1.0   # 1° into each yoga
            y = compute_nithya_yoga(lon, 0.0)
            seen.add(y.index)
        assert len(seen) == 27

    @pytest.mark.parametrize("idx,expected_nature", [
        (0,  "malefic"),    # Vishkambha
        (1,  "benefic"),    # Preeti
        (16, "malefic"),    # Vyatipata
        (26, "malefic"),    # Vaidhriti
    ])
    def test_yoga_natures(self, idx, expected_nature):
        from vedic_astro.engines.panchang_engine import NITHYA_YOGA_NATURE
        assert NITHYA_YOGA_NATURE[idx] == expected_nature

    def test_nithya_yoga_is_distinct_from_astrological_yoga(self):
        """NithyaYoga class must not be confused with YogaResult."""
        from vedic_astro.engines.yoga_dosha_engine import YogaResult
        y = compute_nithya_yoga(10.0, 20.0)
        assert isinstance(y, NithyaYoga)
        assert not isinstance(y, YogaResult)


# ─────────────────────────────────────────────────────────────────────────────
# Karana tests
# ─────────────────────────────────────────────────────────────────────────────

class TestKarana:
    def test_first_karana_is_fixed_kimstughna(self):
        """Sequence number 0 = Kimstughna (fixed)."""
        k = compute_karana(0.0, 0.0)   # diff = 0° → seq = 0
        assert k.sequence_number == 0
        assert k.name == "Kimstughna"
        assert k.is_fixed is True

    def test_second_karana_is_bava(self):
        """Sequence number 1 = first movable karana = Bava."""
        k = compute_karana(0.0, 6.5)   # diff = 6.5° → seq = 1
        assert k.sequence_number == 1
        assert k.name == "Bava"
        assert k.is_fixed is False

    def test_karana_sequence_57_is_shakuni(self):
        """seq 57 = Shakuni (fixed)."""
        diff = 57 * KARANA_SPAN + 1.0  # just inside seq 57
        k = compute_karana(0.0, diff)
        assert k.sequence_number == 57
        assert k.name == "Shakuni"
        assert k.is_fixed is True

    def test_karana_sequence_58_is_chatushpada(self):
        diff = 58 * KARANA_SPAN + 1.0
        k = compute_karana(0.0, diff)
        assert k.sequence_number == 58
        assert k.is_fixed is True

    def test_karana_sequence_59_is_nagava(self):
        diff = 59 * KARANA_SPAN + 1.0
        k = compute_karana(0.0, diff)
        assert k.sequence_number == 59
        assert k.is_fixed is True

    def test_movable_karana_cycles_7(self):
        """Movable karanas repeat every 7 (sequences 1–56)."""
        # seq 1 = Bava, seq 8 = Bava again
        k1 = compute_karana(0.0, 1 * KARANA_SPAN + 0.5)
        k8 = compute_karana(0.0, 8 * KARANA_SPAN + 0.5)
        assert k1.name == k8.name == "Bava"

    def test_vishti_is_7th_movable(self):
        """Vishti (Bhadra) is the 7th movable karana, seq 7."""
        k = compute_karana(0.0, 7 * KARANA_SPAN + 0.5)
        assert k.name == "Vishti"


# ─────────────────────────────────────────────────────────────────────────────
# Auspiciousness
# ─────────────────────────────────────────────────────────────────────────────

class TestAuspiciousness:
    def _make_panchang(self, *, tithi_number=5, paksha="shukla",
                       yoga_nature="benefic", karana_name="Bava",
                       nakshatra_name="Rohini"):
        """Create a minimal PanchangData mock for auspiciousness tests."""
        from unittest.mock import MagicMock
        from vedic_astro.engines.panchang_engine import PanchangData, AyanamshaType
        from datetime import date

        p = MagicMock(spec=PanchangData)
        p.tithi = MagicMock()
        p.tithi.number = tithi_number
        p.tithi.name = "Panchami"
        p.nithya_yoga = MagicMock()
        p.nithya_yoga.nature = yoga_nature
        p.nithya_yoga.name = "Preeti"
        p.karana = MagicMock()
        p.karana.name = karana_name
        p.nakshatra = MagicMock()
        p.nakshatra.name = nakshatra_name
        return p

    def test_auspicious_with_good_elements(self):
        p = self._make_panchang(
            tithi_number=5, yoga_nature="benefic",
            karana_name="Bava", nakshatra_name="Rohini"
        )
        is_auspicious, reasons = is_auspicious_time(p)
        assert is_auspicious is True

    def test_inauspicious_rikta_tithi(self):
        """Tithis 4, 9, 14 are Rikta (inauspicious)."""
        p = self._make_panchang(tithi_number=4)
        is_auspicious, reasons = is_auspicious_time(p)
        assert is_auspicious is False
        assert any("Rikta" in r for r in reasons)

    def test_inauspicious_malefic_yoga(self):
        p = self._make_panchang(yoga_nature="malefic")
        is_auspicious, reasons = is_auspicious_time(p)
        assert is_auspicious is False

    def test_inauspicious_vishti_karana(self):
        p = self._make_panchang(karana_name="Vishti")
        is_auspicious, reasons = is_auspicious_time(p)
        assert is_auspicious is False
        assert any("Vishti" in r for r in reasons)
