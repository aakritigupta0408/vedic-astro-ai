"""
feature_builder.py — Structured astrological feature extraction.

The FeatureBuilder takes outputs from all deterministic engines and
assembles them into a flat, serializable ``AstroFeatures`` object.

This feature set is the bridge between the deterministic computation
layer and the weighted scoring / LLM agent layers.  It is also used
for case similarity matching in the RAG retrieval layer.

Feature categories
------------------
1. **Natal core**        : Signs, houses, longitudes, dignities, retrogrades,
                           combustion, Chara Karakas.
2. **Yogas & Doshas**    : Active yoga names/strengths, dosha names/severities.
3. **Dasha timing**      : Maha/Antar lord, elapsed fractions, lord strengths,
                           mutual friendship, house rulerships.
4. **Transit (Gochara)** : Transit signs, gochara composite strengths, Sade Sati.
5. **Divisional charts** : D9/D10 lagna, planet signs; generalised to all
                           available DivisionalCharts (D1–D60).

Usage
-----
    builder = FeatureBuilder()
    features = builder.build(
        chart=natal_chart,
        dasha_window=window,
        transit_overlay=overlay,
        varga_charts={9: d9_chart, 10: d10_chart},
        yoga_bundle=bundle,
    )
    score = WeightedScorer().score(features, domain="career")
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from vedic_astro.engines.natal_engine import (
    NatalChart, PlanetName, Dignity, SIGN_LORDS, compute_chara_karakas,
    OWN_SIGNS, _EXALTATION, _DEBILITATION, _MOOLATRIKONA,
    _NATURAL_FRIENDS, _NATURAL_ENEMIES,
)


def _d9_dignity_for_sign(planet: str, sign: int) -> str:
    """
    Compute Parashari dignity for *planet* (planet.value string) in *sign* (1-12).
    Used for D9, D10, and other varga positions.
    """
    try:
        pn = PlanetName(planet)
        if sign == _EXALTATION.get(pn):      return "exalted"
        if sign == _DEBILITATION.get(pn):    return "debilitated"
        if sign == _MOOLATRIKONA.get(pn):    return "moolatrikona"
        if sign in OWN_SIGNS.get(pn, set()): return "own"
        sl = SIGN_LORDS.get(sign)
        if sl and sl in _NATURAL_FRIENDS.get(pn, set()):  return "friend"
        if sl and sl in _NATURAL_ENEMIES.get(pn, set()):  return "enemy"
        return "neutral"
    except Exception:
        return "neutral"

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Feature schema
# ─────────────────────────────────────────────────────────────────────────────

class AstroFeatures(BaseModel):
    """
    Flat, serializable feature set assembled from all engine outputs.

    All dict keys use ``PlanetName.value`` strings (e.g. ``"jupiter"``)
    so the object can be round-tripped to/from JSON without enum handling.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    chart_id: str

    # ── Core natal ────────────────────────────────────────────────────────
    lagna_sign: int                           # 1–12
    moon_sign: int
    sun_sign: int
    planet_signs: dict[str, int]              # planet → sign (1–12)
    planet_houses: dict[str, int]             # planet → house (1–12)
    planet_longitudes: dict[str, float]       # planet → 0–360° (sidereal)
    planet_degrees_in_sign: dict[str, float]  # planet → 0–30°
    planet_dignities: dict[str, str]          # planet → dignity.value
    planet_is_retrograde: dict[str, bool]
    planet_is_combust: dict[str, bool]        # within 14° of Sun (excluding Sun itself)

    # ── Karakas (Jaimini) ─────────────────────────────────────────────────
    atmakaraka: str = ""                      # planet.value
    amatyakaraka: str = ""

    # ── Yogas & Doshas ────────────────────────────────────────────────────
    active_yoga_names: list[str] = Field(default_factory=list)
    active_dosha_names: list[str] = Field(default_factory=list)
    yoga_strengths: dict[str, float] = Field(default_factory=dict)
    dosha_severities: dict[str, float] = Field(default_factory=dict)
    net_yoga_strength: float = 0.0
    net_dosha_severity: float = 0.0

    # Yoga structure (for interdependence checks)
    yoga_forming_planets: dict[str, list[str]] = Field(default_factory=dict)
    # yoga_name → [planet.value, …] — planets that form each yoga
    yoga_key_houses: dict[str, list[int]] = Field(default_factory=dict)
    # yoga_name → house numbers involved

    # ── Dasha timing ──────────────────────────────────────────────────────
    maha_lord: str = ""
    antar_lord: str = ""
    maha_elapsed_fraction: float = 0.0        # 0–1
    antar_elapsed_fraction: float = 0.0
    maha_lord_house: int = 0
    maha_lord_sign: int = 0
    maha_lord_dignity: str = "neutral"
    antar_lord_house: int = 0
    antar_lord_sign: int = 0
    antar_lord_dignity: str = "neutral"
    dasha_lords_are_friends: bool = False
    maha_lord_rules_houses: list[int] = Field(default_factory=list)  # houses lord rules natally
    antar_lord_rules_houses: list[int] = Field(default_factory=list)

    # Dasha lord varga depth (D9/D10 dignity — how fully dasha can deliver)
    maha_lord_d9_dignity: str = "neutral"     # dasha lord's dignity in D9
    maha_lord_d10_dignity: str = "neutral"    # dasha lord's dignity in D10 (career)

    # Dasha-Yoga interdependence
    # Yogas whose contributing_planets include the active maha/antar lord
    dasha_activates_yogas: list[str] = Field(default_factory=list)
    antar_activates_yogas: list[str] = Field(default_factory=list)

    # ── Transit (Gochara) ─────────────────────────────────────────────────
    transit_signs: dict[str, int] = Field(default_factory=dict)
    gochara_strengths: dict[str, float] = Field(default_factory=dict)
    gochara_favorable: dict[str, bool] = Field(default_factory=dict)
    sadesati_active: bool = False
    sadesati_phase: Optional[str] = None

    # Transit-Dasha confluence: transiting planet conjunct natal dasha lord (≤5°)
    transit_conjunct_dasha_lord: bool = False
    transit_conjunct_dasha_lord_planet: str = ""   # which transiting planet

    # Transit-Yoga activation: transiting planets over yoga-forming natal planets (≤3°)
    transit_activates_yogas: list[str] = Field(default_factory=list)
    # yoga names whose key planets are hit by current transits

    # Lagna lord placement modifiers
    lagna_lord: str = ""
    lagna_lord_house: int = 0
    lagna_lord_dignity: str = "neutral"

    # ── Divisional charts (D1 is natal) ───────────────────────────────────
    # Keys are division numbers as strings ("9", "10", "3", etc.)
    varga_lagnas: dict[str, int] = Field(default_factory=dict)
    varga_planet_signs: dict[str, dict[str, int]] = Field(default_factory=dict)
    d9_lagna: int = 0
    d9_planet_signs: dict[str, int] = Field(default_factory=dict)
    d10_lagna: int = 0
    d10_planet_signs: dict[str, int] = Field(default_factory=dict)
    atmakaraka_d9_sign: int = 0               # Karakamsha lagna

    model_config = {"frozen": False}


# ─────────────────────────────────────────────────────────────────────────────
# Combustion check
# ─────────────────────────────────────────────────────────────────────────────

_COMBUST_ORBS: dict[str, float] = {
    "moon":    12.0,
    "mars":     8.0,
    "mercury":  4.0,  # retrograde Mercury has wider orb (14°) but we use direct
    "jupiter":  9.0,
    "venus":    9.0,  # retrograde Venus has wider orb but simplified here
    "saturn":  15.0,
}


def _is_combust(sun_lon: float, planet_lon: float, planet: str) -> bool:
    """Return True if planet is within its combustion orb of the Sun."""
    orb = _COMBUST_ORBS.get(planet, 0.0)
    if orb == 0.0:
        return False
    diff = abs(sun_lon - planet_lon) % 360.0
    if diff > 180.0:
        diff = 360.0 - diff
    return diff <= orb


# ─────────────────────────────────────────────────────────────────────────────
# Friendship table (for dasha lord relationship)
# ─────────────────────────────────────────────────────────────────────────────

_NATURAL_FRIENDS: dict[str, set[str]] = {
    "sun":     {"moon", "mars", "jupiter"},
    "moon":    {"sun", "mercury"},
    "mars":    {"sun", "moon", "jupiter"},
    "mercury": {"sun", "venus"},
    "jupiter": {"sun", "moon", "mars"},
    "venus":   {"mercury", "saturn"},
    "saturn":  {"mercury", "venus"},
    "rahu":    {"venus", "saturn"},
    "ketu":    {"mars", "venus", "saturn"},
}


def _planets_are_friends(p1: str, p2: str) -> bool:
    return p2 in _NATURAL_FRIENDS.get(p1, set())


# ─────────────────────────────────────────────────────────────────────────────
# House rulership helper
# ─────────────────────────────────────────────────────────────────────────────

def _houses_ruled_by(planet: str, lagna_sign: int) -> list[int]:
    """
    Return the house numbers ruled by *planet* from *lagna_sign*.

    Uses SIGN_LORDS to determine which signs the planet owns, then converts
    sign numbers to house numbers (house = (sign - lagna) % 12 + 1).
    """
    from vedic_astro.engines.natal_engine import OWN_SIGNS
    try:
        pn = PlanetName(planet)
        owned_signs = OWN_SIGNS.get(pn, set())
        houses = [((sign - lagna_sign) % 12) + 1 for sign in owned_signs]
        return sorted(houses)
    except (ValueError, AttributeError):
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Feature builder
# ─────────────────────────────────────────────────────────────────────────────

class FeatureBuilder:
    """
    Assembles all engine outputs into a flat ``AstroFeatures`` object.

    All parameters except *chart* are optional — the builder gracefully
    uses empty defaults when dasha, transit, or varga data is unavailable.
    """

    def build(
        self,
        chart: NatalChart,
        dasha_window=None,       # DashaWindow | None
        transit_overlay=None,    # TransitOverlay | None
        varga_charts: dict | None = None,  # dict[int, DivisionalChart] | None
        yoga_bundle=None,        # YogaDoshaBundle | None
    ) -> AstroFeatures:
        """
        Build an ``AstroFeatures`` from engine outputs.

        Parameters
        ----------
        chart           : Required. Computed NatalChart (D1).
        dasha_window    : Optional. Active DashaWindow from dasha_engine.
        transit_overlay : Optional. TransitOverlay from transit_engine.
        varga_charts    : Optional. Dict of {division_int: DivisionalChart}.
        yoga_bundle     : Optional. YogaDoshaBundle from yoga_dosha_engine.

        Returns
        -------
        AstroFeatures
        """
        f: dict[str, Any] = {}
        f["chart_id"] = chart.chart_id

        # ── Natal core ────────────────────────────────────────────────────
        self._build_natal(f, chart)

        # ── Yogas & Doshas ────────────────────────────────────────────────
        self._build_yoga_dosha(f, yoga_bundle)

        # ── Dasha ─────────────────────────────────────────────────────────
        self._build_dasha(f, chart, dasha_window)

        # ── Transit ───────────────────────────────────────────────────────
        self._build_transit(f, transit_overlay)

        # ── Divisional charts ─────────────────────────────────────────────
        self._build_vargas(f, varga_charts, f.get("atmakaraka", ""))

        # ── Cross-layer interdependences ──────────────────────────────────
        # Must run AFTER all individual sections (reads from multiple sections)
        self._build_interdependences(f)

        # Strip private/temp keys before constructing model
        f.pop("_transit_longitudes", None)

        return AstroFeatures(**f)

    # ── Private section builders ──────────────────────────────────────────

    @staticmethod
    def _build_natal(f: dict, chart: NatalChart) -> None:
        """Extract natal-only features from NatalChart."""
        sun_lon = chart.planets[PlanetName.SUN].longitude

        planet_signs:          dict[str, int]   = {}
        planet_houses:         dict[str, int]   = {}
        planet_longitudes:     dict[str, float] = {}
        planet_degrees_in_sign: dict[str, float] = {}
        planet_dignities:      dict[str, str]   = {}
        planet_is_retrograde:  dict[str, bool]  = {}
        planet_is_combust:     dict[str, bool]  = {}

        for planet, pos in chart.planets.items():
            pv = planet.value
            planet_signs[pv]            = pos.sign_number
            planet_houses[pv]           = pos.house
            planet_longitudes[pv]       = pos.longitude
            planet_degrees_in_sign[pv]  = pos.longitude % 30.0
            planet_dignities[pv]        = pos.dignity.value
            planet_is_retrograde[pv]    = pos.is_retrograde
            planet_is_combust[pv]       = (
                pv != "sun" and
                _is_combust(sun_lon, pos.longitude, pv)
            )

        f["lagna_sign"]              = chart.lagna_sign
        f["moon_sign"]               = chart.planets[PlanetName.MOON].sign_number
        f["sun_sign"]                = chart.planets[PlanetName.SUN].sign_number
        f["planet_signs"]            = planet_signs
        f["planet_houses"]           = planet_houses
        f["planet_longitudes"]       = planet_longitudes
        f["planet_degrees_in_sign"]  = planet_degrees_in_sign
        f["planet_dignities"]        = planet_dignities
        f["planet_is_retrograde"]    = planet_is_retrograde
        f["planet_is_combust"]       = planet_is_combust

        # Chara Karakas
        try:
            karakas = compute_chara_karakas(chart.planets)
            f["atmakaraka"]  = karakas.get("atmakaraka",  PlanetName.SUN).value
            f["amatyakaraka"] = karakas.get("amatyakaraka", PlanetName.MOON).value
        except Exception:
            f["atmakaraka"]  = ""
            f["amatyakaraka"] = ""

    @staticmethod
    def _build_yoga_dosha(f: dict, bundle) -> None:
        """Extract yoga and dosha features from YogaDoshaBundle."""
        if bundle is None:
            f.update(
                active_yoga_names=[], active_dosha_names=[],
                yoga_strengths={}, dosha_severities={},
                net_yoga_strength=0.0, net_dosha_severity=0.0,
                yoga_forming_planets={}, yoga_key_houses={},
            )
            return

        active_yogas  = bundle.active_yogas
        active_doshas = bundle.active_doshas

        f["active_yoga_names"]  = [y.name for y in active_yogas]
        f["active_dosha_names"] = [d.name for d in active_doshas]
        f["yoga_strengths"]     = {y.name: y.strength for y in active_yogas}
        f["dosha_severities"]   = {d.name: d.severity for d in active_doshas}
        f["net_yoga_strength"]  = bundle.net_yoga_strength
        f["net_dosha_severity"] = (
            sum(d.severity for d in active_doshas) / max(len(active_doshas), 1)
            if active_doshas else 0.0
        )

        # Yoga structure for interdependence checks
        f["yoga_forming_planets"] = {
            y.name: [p.value for p in y.contributing_planets]
            for y in active_yogas
        }
        f["yoga_key_houses"] = {
            y.name: list(y.key_houses)
            for y in active_yogas
        }

    @staticmethod
    def _build_dasha(f: dict, chart: NatalChart, window) -> None:
        """Extract dasha timing features from DashaWindow."""
        if window is None:
            f.update(
                maha_lord="", antar_lord="",
                maha_elapsed_fraction=0.0, antar_elapsed_fraction=0.0,
                maha_lord_house=0, maha_lord_sign=0, maha_lord_dignity="neutral",
                antar_lord_house=0, antar_lord_sign=0, antar_lord_dignity="neutral",
                dasha_lords_are_friends=False,
                maha_lord_rules_houses=[], antar_lord_rules_houses=[],
                maha_lord_d9_dignity="neutral", maha_lord_d10_dignity="neutral",
                dasha_activates_yogas=[], antar_activates_yogas=[],
                lagna_lord="", lagna_lord_house=0, lagna_lord_dignity="neutral",
            )
            return

        maha = window.mahadasha
        antar = window.antardasha
        qdate = window.query_date

        maha_v = maha.lord.value
        antar_v = antar.lord.value if antar else ""

        # Natal placement of dasha lords
        maha_pos  = chart.planets.get(maha.lord)
        antar_pos = chart.planets.get(antar.lord) if antar else None

        f["maha_lord"]             = maha_v
        f["antar_lord"]            = antar_v
        f["maha_elapsed_fraction"] = maha.elapsed_fraction(qdate)
        f["antar_elapsed_fraction"] = antar.elapsed_fraction(qdate) if antar else 0.0

        f["maha_lord_house"]    = maha_pos.house     if maha_pos else 0
        f["maha_lord_sign"]     = maha_pos.sign_number if maha_pos else 0
        f["maha_lord_dignity"]  = maha_pos.dignity.value if maha_pos else "neutral"
        f["antar_lord_house"]   = antar_pos.house    if antar_pos else 0
        f["antar_lord_sign"]    = antar_pos.sign_number if antar_pos else 0
        f["antar_lord_dignity"] = antar_pos.dignity.value if antar_pos else "neutral"

        f["dasha_lords_are_friends"] = _planets_are_friends(maha_v, antar_v)
        f["maha_lord_rules_houses"]  = _houses_ruled_by(maha_v,  chart.lagna_sign)
        f["antar_lord_rules_houses"] = _houses_ruled_by(antar_v, chart.lagna_sign)

        # Lagna lord (needed for interdependence checks)
        try:
            ll = SIGN_LORDS.get(chart.lagna_sign)
            if ll:
                ll_pos = chart.planets.get(ll)
                f["lagna_lord"]         = ll.value
                f["lagna_lord_house"]   = ll_pos.house if ll_pos else 0
                f["lagna_lord_dignity"] = ll_pos.dignity.value if ll_pos else "neutral"
            else:
                f["lagna_lord"] = ""
                f["lagna_lord_house"] = 0
                f["lagna_lord_dignity"] = "neutral"
        except Exception:
            f["lagna_lord"] = ""
            f["lagna_lord_house"] = 0
            f["lagna_lord_dignity"] = "neutral"

        # Placeholder fields filled later by _build_interdependences
        f["maha_lord_d9_dignity"]  = "neutral"
        f["maha_lord_d10_dignity"] = "neutral"
        f["dasha_activates_yogas"] = []
        f["antar_activates_yogas"] = []

    @staticmethod
    def _build_transit(f: dict, overlay) -> None:
        """Extract transit/gochara features from TransitOverlay."""
        if overlay is None:
            f.update(
                transit_signs={}, gochara_strengths={}, gochara_favorable={},
                sadesati_active=False, sadesati_phase=None,
                transit_conjunct_dasha_lord=False, transit_conjunct_dasha_lord_planet="",
                transit_activates_yogas=[],
            )
            return

        transit_signs: dict[str, int]   = {}
        gochara_strengths: dict[str, float] = {}
        gochara_favorable: dict[str, bool]  = {}

        # Transit longitudes (for conjunction checks)
        transit_longitudes: dict[str, float] = {}

        for planet, pos in overlay.snapshot.positions.items():
            transit_signs[planet.value] = pos.sign_number
            transit_longitudes[planet.value] = pos.longitude

        for planet, strength in overlay.gochara.items():
            gochara_strengths[planet.value] = strength.composite_strength
            gochara_favorable[planet.value] = strength.is_favorable

        f["transit_signs"]     = transit_signs
        f["gochara_strengths"] = gochara_strengths
        f["gochara_favorable"] = gochara_favorable
        f["sadesati_active"]   = overlay.sadesati_active
        f["sadesati_phase"]    = overlay.sadesati_phase

        # Store transit longitudes for interdependence computation
        # (computed later when we have both natal and transit data)
        f["_transit_longitudes"] = transit_longitudes  # private; used by _build_interdependences

    @staticmethod
    def _build_vargas(
        f: dict,
        varga_charts: dict | None,
        atmakaraka: str,
    ) -> None:
        """Extract divisional chart features."""
        if not varga_charts:
            f.update(
                varga_lagnas={}, varga_planet_signs={},
                d9_lagna=0, d9_planet_signs={},
                d10_lagna=0, d10_planet_signs={},
                atmakaraka_d9_sign=0,
            )
            return

        varga_lagnas: dict[str, int] = {}
        varga_planet_signs: dict[str, dict[str, int]] = {}

        for div, vc in varga_charts.items():
            k = str(div)
            varga_lagnas[k] = vc.lagna_sign
            varga_planet_signs[k] = {
                p.value: pos.sign_number for p, pos in vc.planets.items()
            }

        f["varga_lagnas"]       = varga_lagnas
        f["varga_planet_signs"] = varga_planet_signs

        # D9 convenience fields
        d9 = varga_charts.get(9)
        f["d9_lagna"]       = d9.lagna_sign if d9 else 0
        f["d9_planet_signs"] = varga_planet_signs.get("9", {})

        # D10 convenience fields
        d10 = varga_charts.get(10)
        f["d10_lagna"]       = d10.lagna_sign if d10 else 0
        f["d10_planet_signs"] = varga_planet_signs.get("10", {})

        # Karakamsha: atmakaraka's sign in D9
        if atmakaraka and d9:
            try:
                ak = PlanetName(atmakaraka)
                f["atmakaraka_d9_sign"] = d9.planets[ak].sign_number if ak in d9.planets else 0
            except (ValueError, KeyError):
                f["atmakaraka_d9_sign"] = 0
        else:
            f["atmakaraka_d9_sign"] = 0

    @staticmethod
    def _build_interdependences(f: dict) -> None:
        """
        Compute cross-layer interdependence features.

        This runs AFTER all individual section builders so it can read
        from natal, yoga, dasha, transit, and varga sections simultaneously.

        Fills:
        - maha_lord_d9_dignity / maha_lord_d10_dignity
        - dasha_activates_yogas / antar_activates_yogas
        - transit_conjunct_dasha_lord / transit_conjunct_dasha_lord_planet
        - transit_activates_yogas
        """
        # ── 1. Dasha lord varga depth ──────────────────────────────────────
        # What is the dasha lord's dignity in D9 and D10?
        # This modifies how fully the dasha promise can manifest.
        maha_v = f.get("maha_lord", "")
        if maha_v:
            d9_signs = f.get("d9_planet_signs", {})
            d10_signs = f.get("d10_planet_signs", {})
            if d9_signs:
                d9_sign = d9_signs.get(maha_v)
                if d9_sign:
                    f["maha_lord_d9_dignity"] = _d9_dignity_for_sign(maha_v, d9_sign)
            if d10_signs:
                d10_sign = d10_signs.get(maha_v)
                if d10_sign:
                    f["maha_lord_d10_dignity"] = _d9_dignity_for_sign(maha_v, d10_sign)

        # ── 2. Dasha-Yoga activation ───────────────────────────────────────
        # A yoga is "activated" by the dasha if the maha/antar lord is one of
        # the yoga-forming planets, OR if the dasha lord rules a key yoga house.
        yoga_planets = f.get("yoga_forming_planets", {})   # yoga_name → [planet_values]
        yoga_houses  = f.get("yoga_key_houses", {})        # yoga_name → [house numbers]
        antar_v      = f.get("antar_lord", "")
        maha_rules   = set(f.get("maha_lord_rules_houses", []))
        antar_rules  = set(f.get("antar_lord_rules_houses", []))

        dasha_activated: list[str] = []
        antar_activated: list[str] = []
        for yoga_name, planets in yoga_planets.items():
            # Direct: dasha lord IS a yoga planet
            if maha_v and maha_v in planets:
                dasha_activated.append(yoga_name)
            # Indirect: dasha lord rules a key house of the yoga
            elif maha_rules & set(yoga_houses.get(yoga_name, [])):
                dasha_activated.append(yoga_name)

            if antar_v and antar_v in planets:
                antar_activated.append(yoga_name)
            elif antar_rules & set(yoga_houses.get(yoga_name, [])):
                antar_activated.append(yoga_name)

        f["dasha_activates_yogas"] = dasha_activated
        f["antar_activates_yogas"] = antar_activated

        # ── 3. Transit-Dasha confluence ────────────────────────────────────
        # Is any transiting planet conjunct (within 5°) the natal dasha lord?
        # This is the "double activation" — same planet's timing in two systems.
        transit_lons = f.get("_transit_longitudes", {})    # planet → transit longitude
        natal_lons   = f.get("planet_longitudes", {})      # planet → natal longitude

        conj_planet = ""
        conj_found  = False
        if maha_v and transit_lons and natal_lons:
            natal_dasha_lon = natal_lons.get(maha_v)
            if natal_dasha_lon is not None:
                for t_planet, t_lon in transit_lons.items():
                    diff = abs(t_lon - natal_dasha_lon) % 360.0
                    if diff > 180.0:
                        diff = 360.0 - diff
                    if diff <= 5.0:          # conjunction orb: 5°
                        conj_found  = True
                        conj_planet = t_planet
                        break
                    # Also check opposition (180° aspect, within 4°)
                    if abs(diff - 180.0) <= 4.0:
                        conj_found  = True
                        conj_planet = f"{t_planet}(opp)"
                        break

        f["transit_conjunct_dasha_lord"] = conj_found
        f["transit_conjunct_dasha_lord_planet"] = conj_planet

        # ── 4. Transit-Yoga activation ─────────────────────────────────────
        # A yoga is "transit-activated" if any transiting planet is within 3°
        # of the natal longitude of any of the yoga's forming planets.
        transit_activated_yogas: list[str] = []
        if transit_lons and natal_lons:
            for yoga_name, planets in yoga_planets.items():
                triggered = False
                for yoga_planet in planets:
                    natal_lon = natal_lons.get(yoga_planet)
                    if natal_lon is None:
                        continue
                    for t_lon in transit_lons.values():
                        diff = abs(t_lon - natal_lon) % 360.0
                        if diff > 180.0:
                            diff = 360.0 - diff
                        if diff <= 3.0:      # tight conjunction orb: 3°
                            triggered = True
                            break
                    if triggered:
                        break
                if triggered:
                    transit_activated_yogas.append(yoga_name)

        f["transit_activates_yogas"] = transit_activated_yogas
