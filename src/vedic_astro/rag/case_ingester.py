"""
case_ingester.py — VedAstro dataset integration pipeline.

Responsibility
--------------
1. Load raw VedAstro JSON exports from ``data/raw/vedastro/``.
2. Geocode each birth location (OpenCage or fallback table).
3. Optionally compute NatalChart per case (requires pyswisseph).
4. Compute a structured feature set for retrieval similarity matching.
5. Build a human-readable case summary for LLM prompt injection.
6. Write ``data/raw/vedastro/cases.json`` (indexed by ``case_id``).

Case record schema
------------------
Each persisted case record includes:
    - Raw birth data (year/month/day/hour/minute/place/lat/lon)
    - Computed features: lagna_sign, moon_sign, maha_lord, active_yogas, ...
    - ``summary`` : 1-2 sentence narrative for RAG injection into prompts
    - ``notes``   : Any existing notes from the VedAstro export
    - ``tags``    : Keyword tags (career/marriage/health)

Usage (offline pipeline)
------------------------
    ingester = CaseIngester()
    cases = await ingester.ingest(Path("data/raw/vedastro"))
    # cases saved to data/raw/vedastro/cases.json automatically
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Case record schema
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CaseRecord:
    """
    A single reference case from the VedAstro dataset.

    ``features`` is a flat dict of astrological features used for
    structural similarity matching during retrieval.
    """
    case_id: str
    name: str
    year: int
    month: int
    day: int
    hour: int
    minute: int
    place: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    timezone_str: str = "UTC"
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    # Features populated post-computation
    lagna_sign: Optional[int] = None
    moon_sign: Optional[int] = None
    maha_lord: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Ingester
# ─────────────────────────────────────────────────────────────────────────────

class CaseIngester:
    """
    Offline pipeline: raw VedAstro JSON → structured CaseRecord list.

    Parameters
    ----------
    compute_charts : If True, compute NatalChart for each case (requires
                     pyswisseph). If False, only geocoding and note parsing
                     are performed.
    max_cases      : Limit total cases processed (useful for testing).
    concurrency    : Parallel geocoding + chart requests.
    """

    def __init__(
        self,
        compute_charts: bool = True,
        max_cases: Optional[int] = None,
        concurrency: int = 4,
    ) -> None:
        self._compute_charts = compute_charts
        self._max_cases = max_cases
        self._concurrency = concurrency

    # ── Public API ────────────────────────────────────────────────────────

    async def ingest(self, data_dir: Path) -> list[CaseRecord]:
        """
        Load all VedAstro JSON files from *data_dir* and build case records.

        Writes results to ``{data_dir}/cases.json``.
        Returns the list of CaseRecord objects.
        """
        raw_entries = self._load_raw(data_dir)
        if self._max_cases:
            raw_entries = raw_entries[: self._max_cases]

        logger.info("CaseIngester: processing %d raw entries", len(raw_entries))

        sem = asyncio.Semaphore(self._concurrency)

        async def process_entry(entry: dict) -> Optional[CaseRecord]:
            async with sem:
                return await self._build_case(entry)

        results = await asyncio.gather(*[process_entry(e) for e in raw_entries])
        cases = [r for r in results if r is not None]

        out_path = data_dir / "cases.json"
        out_path.write_text(
            json.dumps([asdict(c) for c in cases], indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("CaseIngester: %d cases → %s", len(cases), out_path)
        return cases

    # ── Raw loading ───────────────────────────────────────────────────────

    @staticmethod
    def _load_raw(data_dir: Path) -> list[dict]:
        """Collect all JSON records from the data directory."""
        if not data_dir.exists():
            logger.warning("Data directory not found: %s", data_dir)
            return []

        entries = []
        for path in sorted(data_dir.glob("*.json")):
            if path.name == "cases.json":
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Skip %s: %s", path.name, exc)
                continue

            if isinstance(data, list):
                entries.extend(data)
            elif isinstance(data, dict):
                entries.append(data)

        logger.info("Loaded %d raw entries from %s", len(entries), data_dir)
        return entries

    # ── Case building ─────────────────────────────────────────────────────

    async def _build_case(self, entry: dict) -> Optional[CaseRecord]:
        """Convert a raw dict to a CaseRecord, geocoding and computing features."""
        birth = self._parse_birth(entry)
        if birth is None:
            return None

        case_id = self._make_case_id(birth)

        # Geocode if needed
        lat, lon, tz = birth["lat"], birth["lon"], birth["tz"]
        if lat is None:
            lat, lon, tz = await self._geocode(birth["place"])

        # Build base record
        record = CaseRecord(
            case_id=case_id,
            name=birth["name"],
            year=birth["year"], month=birth["month"], day=birth["day"],
            hour=birth["hour"], minute=birth["minute"],
            place=birth["place"],
            lat=lat, lon=lon, timezone_str=tz,
            notes=birth["notes"],
            tags=birth["tags"],
        )

        # Compute chart features (optional)
        if self._compute_charts and lat is not None:
            features = await self._compute_features(record)
            record.features = features
            record.lagna_sign  = features.get("lagna_sign")
            record.moon_sign   = features.get("moon_sign")
            record.maha_lord   = features.get("maha_lord")

        record.summary = self._build_summary(record)
        return record

    @staticmethod
    def _parse_birth(entry: dict) -> Optional[dict]:
        """Extract and validate birth fields from a raw dict."""
        try:
            year  = int(entry.get("BirthYear",  entry.get("year",  0)))
            month = int(entry.get("BirthMonth", entry.get("month", 0)))
            day   = int(entry.get("BirthDay",   entry.get("day",   0)))
            hour  = int(entry.get("BirthHour",  entry.get("hour",  0)))
            minute = int(entry.get("BirthMinute", entry.get("minute", 0)))
            place = str(entry.get("BirthLocation", entry.get("place", ""))).strip()
            name  = str(entry.get("Name", entry.get("name", "Unknown"))).strip()
            notes = str(entry.get("Notes", entry.get("notes", ""))).strip()
            tags  = list(entry.get("Tags", entry.get("tags", [])))

            # Direct lat/lon if present
            lat = entry.get("Latitude",  entry.get("lat"))
            lon = entry.get("Longitude", entry.get("lon"))
            tz  = entry.get("Timezone",  entry.get("timezone_str", "UTC"))

            if not year or not month or not day:
                return None

        except (TypeError, ValueError):
            return None

        return dict(
            year=year, month=month, day=day, hour=hour, minute=minute,
            place=place, name=name, notes=notes, tags=tags,
            lat=float(lat) if lat is not None else None,
            lon=float(lon) if lon is not None else None,
            tz=tz,
        )

    @staticmethod
    def _make_case_id(birth: dict) -> str:
        import hashlib
        payload = f"{birth['year']}-{birth['month']}-{birth['day']}|{birth['hour']}:{birth['minute']}|{birth['place']}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    @staticmethod
    async def _geocode(place: str) -> tuple[Optional[float], Optional[float], str]:
        """Return (lat, lon, timezone_str) for a place name."""
        if not place:
            return None, None, "UTC"
        try:
            from vedic_astro.tools.geo import get_geo_resolver
            resolver = get_geo_resolver()
            loc = await resolver.resolve(place)
            return loc.lat, loc.lon, loc.timezone
        except Exception as exc:
            logger.debug("Geocode failed for %r: %s", place, exc)
            return None, None, "UTC"

    async def _compute_features(self, record: CaseRecord) -> dict[str, Any]:
        """
        Compute astrological features for a case.

        Returns a flat dict that FeatureBuilder would return for retrieval.
        Gracefully returns empty dict if pyswisseph unavailable.
        """
        try:
            import asyncio as _asyncio
            from vedic_astro.engines.natal_engine import build_natal_chart, PlanetName
            from vedic_astro.engines.dasha_engine import get_active_dasha_window

            chart = await _asyncio.to_thread(
                build_natal_chart,
                record.year, record.month, record.day,
                record.hour, record.minute,
                record.lat, record.lon,
            )

            query_date = date(record.year, record.month, record.day)  # birth date as proxy
            birth_dt   = datetime(record.year, record.month, record.day,
                                  record.hour, record.minute)
            moon_lon = chart.planets[PlanetName.MOON].longitude

            try:
                dasha_window = await _asyncio.to_thread(
                    get_active_dasha_window,
                    moon_lon, birth_dt, query_date, chart, 2,
                )
                maha_lord = dasha_window.mahadasha.lord.value
            except Exception:
                maha_lord = None

            features: dict[str, Any] = {
                "lagna_sign": chart.lagna_sign,
                "moon_sign":  chart.planets[PlanetName.MOON].sign_number,
                "sun_sign":   chart.planets[PlanetName.SUN].sign_number,
                "maha_lord":  maha_lord,
                "planet_signs": {p.value: pos.sign_number for p, pos in chart.planets.items()},
                "planet_houses": {p.value: pos.house for p, pos in chart.planets.items()},
                "planet_dignities": {p.value: pos.dignity.value for p, pos in chart.planets.items()},
            }
            return features

        except ImportError:
            logger.debug("pyswisseph not available — skipping chart computation for case %s", record.case_id)
            return {}
        except Exception as exc:
            logger.warning("Feature computation failed for case %s: %s", record.case_id, exc)
            return {}

    @staticmethod
    def _build_summary(record: CaseRecord) -> str:
        """
        Build a 1-2 sentence case summary for RAG injection.

        Format: ``{name} ({year}): {notes excerpt}. Features: lagna={lagna}, moon={moon}, maha={maha}.``
        """
        parts = [f"{record.name} ({record.year})"]

        if record.notes:
            excerpt = record.notes[:200].rstrip()
            if not excerpt.endswith("."):
                excerpt += "."
            parts.append(excerpt)

        feat_parts = []
        if record.lagna_sign:
            from vedic_astro.engines.natal_engine import RASHI_NAMES
            try:
                lagna_name = RASHI_NAMES[record.lagna_sign - 1]
                moon_name  = RASHI_NAMES[record.moon_sign - 1] if record.moon_sign else "?"
                feat_parts.append(f"Lagna={lagna_name}, Moon={moon_name}")
            except (IndexError, TypeError):
                pass
        if record.maha_lord:
            feat_parts.append(f"Dasha={record.maha_lord.title()}")
        if record.tags:
            feat_parts.append("Tags: " + ", ".join(record.tags[:4]))

        if feat_parts:
            parts.append("Features: " + "; ".join(feat_parts) + ".")

        return " ".join(parts)
