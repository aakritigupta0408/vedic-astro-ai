"""
geo.py — Geographic resolver: place name → lat/lon/timezone.

Strategy
--------
1. Check Redis cache first (permanent TTL — city coordinates don't change).
2. Query OpenCage Geocoding API if API key is configured.
3. Fall back to a small hardcoded lookup table of major cities so the
   system can operate without any geocoding API during development/testing.

The resolved ``GeoLocation`` is what gets embedded into the chart birth data
and ultimately into the cache key, so every call with the same query must
return bit-identical coordinates.

Usage
-----
    resolver = get_geo_resolver()
    loc = await resolver.resolve("Mumbai, India")
    print(loc.lat, loc.lon, loc.timezone)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GeoLocation:
    """Resolved geographic location."""
    query: str          # original query string
    lat: float          # decimal degrees, positive = N
    lon: float          # decimal degrees, positive = E
    timezone: str       # IANA timezone, e.g. "Asia/Kolkata"
    display_name: str   # human-readable name returned by geocoder
    source: str         # "cache" | "opencage" | "fallback"


# ─────────────────────────────────────────────────────────────────────────────
# Hardcoded fallback table
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK: dict[str, tuple[float, float, str]] = {
    # query_lower: (lat, lon, timezone)
    "mumbai":           (19.0760,  72.8777, "Asia/Kolkata"),
    "mumbai, india":    (19.0760,  72.8777, "Asia/Kolkata"),
    "delhi":            (28.6139,  77.2090, "Asia/Kolkata"),
    "delhi, india":     (28.6139,  77.2090, "Asia/Kolkata"),
    "new delhi":        (28.6139,  77.2090, "Asia/Kolkata"),
    "new delhi, india": (28.6139,  77.2090, "Asia/Kolkata"),
    "bangalore":        (12.9716,  77.5946, "Asia/Kolkata"),
    "bengaluru":        (12.9716,  77.5946, "Asia/Kolkata"),
    "chennai":          (13.0827,  80.2707, "Asia/Kolkata"),
    "kolkata":          (22.5726,  88.3639, "Asia/Kolkata"),
    "hyderabad":        (17.3850,  78.4867, "Asia/Kolkata"),
    "pune":             (18.5204,  73.8567, "Asia/Kolkata"),
    "ahmedabad":        (23.0225,  72.5714, "Asia/Kolkata"),
    "jaipur":           (26.9124,  75.7873, "Asia/Kolkata"),
    "varanasi":         (25.3176,  82.9739, "Asia/Kolkata"),
    "london":           (51.5074,  -0.1278, "Europe/London"),
    "new york":         (40.7128, -74.0060, "America/New_York"),
    "new york, usa":    (40.7128, -74.0060, "America/New_York"),
    "los angeles":      (34.0522,-118.2437, "America/Los_Angeles"),
    "chicago":          (41.8781, -87.6298, "America/Chicago"),
    "toronto":          (43.6532, -79.3832, "America/Toronto"),
    "sydney":           (-33.8688, 151.2093, "Australia/Sydney"),
    "singapore":        (1.3521,  103.8198, "Asia/Singapore"),
    "dubai":            (25.2048,  55.2708, "Asia/Dubai"),
    "berlin":           (52.5200,  13.4050, "Europe/Berlin"),
    "paris":            (48.8566,   2.3522, "Europe/Paris"),
    "tokyo":            (35.6762, 139.6503, "Asia/Tokyo"),
}


def _fallback_lookup(query: str) -> Optional[GeoLocation]:
    key = query.strip().lower()
    if key in _FALLBACK:
        lat, lon, tz = _FALLBACK[key]
        return GeoLocation(
            query=query,
            lat=lat,
            lon=lon,
            timezone=tz,
            display_name=query.title(),
            source="fallback",
        )
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Resolver
# ─────────────────────────────────────────────────────────────────────────────

class GeoResolver:
    """
    Async geographic resolver.

    Lookup order:
    1. Redis cache (permanent)
    2. OpenCage API (if key configured)
    3. Hardcoded fallback table
    """

    def __init__(self, opencage_api_key: Optional[str] = None) -> None:
        self._api_key = opencage_api_key

    async def resolve(self, query: str) -> GeoLocation:
        """
        Resolve *query* to a ``GeoLocation``.

        Parameters
        ----------
        query : str
            Place name (e.g. ``"Mumbai, India"``) or ``"lat,lon"`` pair.

        Returns
        -------
        GeoLocation

        Raises
        ------
        ValueError
            If the location cannot be resolved by any available method.
        """
        # 0. Lat/lon passthrough  ("19.076,72.877")
        loc = self._try_latlon_string(query)
        if loc:
            return loc

        from vedic_astro.tools.hasher import make_geo_key
        from vedic_astro.tools.cache import get_cache

        cache_key = make_geo_key(query)
        cache = get_cache()

        # 1. Cache
        cached = await cache.get(cache_key)
        if cached:
            return GeoLocation(**cached, source="cache")

        # 2. OpenCage
        if self._api_key:
            loc = await self._opencage(query)
            if loc:
                from vedic_astro.settings import settings
                await cache.set(cache_key, {
                    "query": loc.query,
                    "lat": loc.lat,
                    "lon": loc.lon,
                    "timezone": loc.timezone,
                    "display_name": loc.display_name,
                }, ttl=settings.geo_cache_ttl)
                return loc

        # 3. Fallback table
        loc = _fallback_lookup(query)
        if loc:
            return loc

        raise ValueError(
            f"Cannot resolve location: {query!r}. "
            "Set OPENCAGE_API_KEY in .env or use 'lat,lon' format."
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _try_latlon_string(query: str) -> Optional[GeoLocation]:
        """Parse ``"19.076,72.877"`` or ``"19.076, 72.877"``."""
        parts = query.replace(" ", "").split(",")
        if len(parts) == 2:
            try:
                lat = float(parts[0])
                lon = float(parts[1])
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    import timezonefinder  # type: ignore[import]
                    tf = timezonefinder.TimezoneFinder()
                    tz = tf.timezone_at(lat=lat, lng=lon) or "UTC"
                    return GeoLocation(
                        query=query,
                        lat=lat,
                        lon=lon,
                        timezone=tz,
                        display_name=f"{lat:.4f}, {lon:.4f}",
                        source="passthrough",
                    )
            except (ValueError, ImportError):
                pass
        return None

    async def _opencage(self, query: str) -> Optional[GeoLocation]:
        """Call the OpenCage geocoding API."""
        try:
            import httpx  # type: ignore[import]
        except ImportError:
            logger.warning("httpx not installed — OpenCage geocoding unavailable")
            return None

        params = {
            "q": query,
            "key": self._api_key,
            "limit": 1,
            "no_annotations": 0,
        }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://api.opencagedata.com/geocode/v1/json",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

            if not data.get("results"):
                logger.warning("OpenCage: no results for %r", query)
                return None

            result = data["results"][0]
            geometry = result["geometry"]
            timezone = result.get("annotations", {}).get("timezone", {}).get("name", "UTC")

            return GeoLocation(
                query=query,
                lat=geometry["lat"],
                lon=geometry["lng"],
                timezone=timezone,
                display_name=result.get("formatted", query),
                source="opencage",
            )
        except Exception as exc:
            logger.warning("OpenCage error for %r: %s", query, exc)
            return None


# ─────────────────────────────────────────────────────────────────────────────
# Singleton factory
# ─────────────────────────────────────────────────────────────────────────────

_geo_instance: Optional[GeoResolver] = None


def get_geo_resolver() -> GeoResolver:
    """Return the application-wide GeoResolver singleton."""
    global _geo_instance
    if _geo_instance is None:
        from vedic_astro.settings import settings
        _geo_instance = GeoResolver(opencage_api_key=settings.opencage_api_key)
    return _geo_instance
