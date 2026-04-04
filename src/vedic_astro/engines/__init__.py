"""
engines — Pure deterministic computation layer.

Zero LLM calls. All modules in this package are side-effect-free
mathematical functions over astronomical and Vedic rule data.

Public surface (re-exported for convenience):
"""

from vedic_astro.engines.natal_engine import (
    AyanamshaType,
    BhavaData,
    Dignity,
    NakshatraData,
    NatalChart,
    NAKSHATRA_LORDS,
    NAKSHATRA_NAMES,
    OWN_SIGNS,
    PlanetName,
    PlanetPosition,
    RetrogradeDignityRule,
    RASHI_NAMES,
    SIGN_LORDS,
    ShadBala,
    build_natal_chart,
    chart_fingerprint,
    compute_ayanamsha,
    compute_dignity,
    compute_julian_day,
    compute_nakshatra,
    longitude_to_sign,
    tropical_to_sidereal,
)

from vedic_astro.engines.dasha_engine import (
    DashaPeriod,
    DashaWindow,
    DashaLordStrength,
    VIMSHOTTARI_SEQUENCE,
    VIMSHOTTARI_YEARS,
    VIMSHOTTARI_INDEX,
    compute_maha_dashas,
    compute_antar_dashas,
    compute_pratyantar_dashas,
    compute_sookshma_dashas,
    get_active_dasha_window,
    get_upcoming_dasha_windows,
)

from vedic_astro.engines.varga_engine import (
    DivisionalChart,
    DivisionalPosition,
    InsufficientPrecisionError,
    PRECISION_REQUIREMENTS,
    compute_divisional_chart,
    compute_required_charts,
    list_registered_divisions,
)

from vedic_astro.engines.transit_engine import (
    AspectType,
    GocharyaStrength,
    TransitAspect,
    TransitOverlay,
    TransitPosition,
    TransitSnapshot,
    compute_transit_snapshot,
    compute_transit_overlay,
    compute_gochara_strength,
    get_transits_for_date,
)

from vedic_astro.engines.panchang_engine import (
    Karana,
    NithyaYoga,
    PanchangData,
    Tithi,
    Vara,
    compute_panchang,
    compute_tithi,
    compute_nithya_yoga,
    compute_karana,
    compute_vara,
    is_auspicious_time,
)

from vedic_astro.engines.yoga_dosha_engine import (
    DoshaCategory,
    DoshaResult,
    YogaCategory,
    YogaDoshaBundle,
    YogaResult,
    YogaSeverity,
    detect_all_yogas,
    detect_all_doshas,
    detect_all_yogas_and_doshas,
)

__all__ = [
    # natal
    "AyanamshaType", "BhavaData", "Dignity", "NakshatraData", "NatalChart",
    "NAKSHATRA_LORDS", "NAKSHATRA_NAMES", "OWN_SIGNS", "PlanetName",
    "PlanetPosition", "RetrogradeDignityRule", "RASHI_NAMES", "SIGN_LORDS",
    "ShadBala", "build_natal_chart", "chart_fingerprint",
    # dasha
    "DashaPeriod", "DashaWindow", "DashaLordStrength",
    "VIMSHOTTARI_SEQUENCE", "VIMSHOTTARI_YEARS",
    "get_active_dasha_window", "get_upcoming_dasha_windows",
    # varga
    "DivisionalChart", "DivisionalPosition", "InsufficientPrecisionError",
    "compute_divisional_chart", "compute_required_charts",
    # transit
    "TransitSnapshot", "TransitOverlay", "GocharyaStrength",
    "compute_transit_snapshot", "compute_transit_overlay",
    # panchang
    "PanchangData", "Tithi", "NithyaYoga", "Karana", "Vara",
    "compute_panchang",
    # yoga/dosha
    "YogaResult", "DoshaResult", "YogaDoshaBundle",
    "detect_all_yogas_and_doshas",
]
