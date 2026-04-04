"""
report_repo.py — MongoDB repository for final reading reports.

A report is the complete output of one pipeline run: the synthesised
narrative, critic score, revision flag, and all agent sub-outputs.

Documents are keyed by ``(chart_id, query_hash)`` to allow the same
chart to have multiple readings for different queries.

Usage
-----
    repo = ReportRepository(await get_mongo_db())
    await repo.save(chart_id, query_hash, report_dict)
    report = await repo.find(chart_id, query_hash)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_COLLECTION = "reports"


def _query_hash(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode()).hexdigest()[:16]


class ReportRepository:
    def __init__(self, db) -> None:
        self._col = db[_COLLECTION]

    async def save(
        self,
        chart_id: str,
        query: str,
        report: dict[str, Any],
    ) -> str:
        """
        Persist a report document.

        Returns
        -------
        str
            Composite document ID: ``{chart_id}:{query_hash}``.
        """
        qhash = _query_hash(query)
        doc_id = f"{chart_id}:{qhash}"
        doc = {
            "_id": doc_id,
            "chart_id": chart_id,
            "query_hash": qhash,
            "query": query,
            "report": report,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await self._col.replace_one({"_id": doc_id}, doc, upsert=True)
            logger.debug("Report saved: %s", doc_id)
        except Exception as exc:
            logger.error("Report save error: %s", exc)
            raise
        return doc_id

    async def find(
        self,
        chart_id: str,
        query: str,
    ) -> Optional[dict[str, Any]]:
        """Retrieve a report by (chart_id, query). Returns None on miss."""
        doc_id = f"{chart_id}:{_query_hash(query)}"
        doc = await self._col.find_one({"_id": doc_id})
        if doc is None:
            return None
        return doc["report"]

    async def list_for_chart(
        self,
        chart_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return the most recent reports for a given chart_id."""
        cursor = (
            self._col.find({"chart_id": chart_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        return [doc["report"] async for doc in cursor]
