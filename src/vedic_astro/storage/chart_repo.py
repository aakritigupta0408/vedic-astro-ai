"""
chart_repo.py — MongoDB repository for NatalChart documents.

Each chart document is stored with ``_id = chart_id`` (sha256 fingerprint).
Charts are immutable once stored — birth data never changes.

Usage
-----
    repo = ChartRepository(await get_mongo_db())
    await repo.save(chart)
    chart = await repo.find(chart_id)
"""

from __future__ import annotations

import logging
from typing import Optional

from vedic_astro.engines.natal_engine import NatalChart

logger = logging.getLogger(__name__)

_COLLECTION = "charts"


class ChartRepository:
    def __init__(self, db) -> None:
        self._col = db[_COLLECTION]

    async def save(self, chart: NatalChart) -> str:
        """
        Persist a NatalChart. Idempotent — duplicate inserts are silently ignored.

        Returns
        -------
        str
            The chart_id used as ``_id``.
        """
        doc = chart.model_dump()
        doc["_id"] = chart.chart_id
        try:
            await self._col.insert_one(doc)
            logger.debug("Chart saved: %s", chart.chart_id)
        except Exception as exc:
            if "duplicate key" in str(exc).lower() or "E11000" in str(exc):
                logger.debug("Chart already exists: %s", chart.chart_id)
            else:
                raise
        return chart.chart_id

    async def find(self, chart_id: str) -> Optional[NatalChart]:
        """
        Retrieve a NatalChart by its fingerprint ID.

        Returns ``None`` if not found.
        """
        doc = await self._col.find_one({"_id": chart_id})
        if doc is None:
            return None
        doc.pop("_id", None)
        return NatalChart.model_validate(doc)

    async def delete(self, chart_id: str) -> bool:
        """Delete a chart document. Returns True if deleted."""
        result = await self._col.delete_one({"_id": chart_id})
        return result.deleted_count > 0

    async def exists(self, chart_id: str) -> bool:
        """Check if a chart exists without fetching the full document."""
        count = await self._col.count_documents({"_id": chart_id}, limit=1)
        return count > 0
