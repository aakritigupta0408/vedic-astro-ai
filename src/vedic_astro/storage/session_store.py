"""
session_store.py — Session storage with MongoDB backend and in-memory fallback.

A session tracks one user's conversation: birth data, query history, and
the most recent reading per query.  Sessions persist across page refreshes.

Session schema (MongoDB document)
----------------------------------
{
  "_id": "<uuid4>",
  "created_at": "<ISO datetime>",
  "updated_at": "<ISO datetime>",
  "birth_data": { year, month, day, hour, minute, place, lat, lon, timezone_str },
  "chart_id": "<sha256[:16]>",
  "queries": [
    {
      "query": "<user question>",
      "domain": "<career|...>",
      "query_date": "<YYYY-MM-DD>",
      "reading_summary": "<first 300 chars of final_reading>",
      "score": 0.72,
      "interpretation": "strong_positive",
      "was_revised": false,
      "timestamp": "<ISO datetime>"
    },
    ...
  ]
}

In-memory fallback
------------------
``InMemorySessionStore`` provides an identical interface without MongoDB.
It is used automatically when MongoDB is unavailable.  Data is lost on
restart (appropriate for development and HF Spaces free tier).

Usage
-----
    store = SessionStoreFactory.create()   # auto-selects Mongo or in-memory
    session_id = await store.create_session(birth_data, chart_id)
    await store.add_query(session_id, query, reading)
    history = await store.get_history(session_id)
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Abstract interface
# ─────────────────────────────────────────────────────────────────────────────

class AbstractSessionStore(ABC):
    """Common async interface for all session store implementations."""

    @abstractmethod
    async def create_session(
        self,
        birth_data: dict[str, Any],
        chart_id: str,
    ) -> str:
        """Create a new session and return session_id."""
        ...

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a full session document."""
        ...

    @abstractmethod
    async def add_query(
        self,
        session_id: str,
        query: str,
        domain: str,
        reading_summary: str,
        score: float,
        interpretation: str,
        was_revised: bool,
    ) -> None:
        """Append a query result to the session's history."""
        ...

    @abstractmethod
    async def get_history(self, session_id: str) -> list[dict[str, Any]]:
        """Return the list of past queries for a session."""
        ...

    @abstractmethod
    async def session_exists(self, session_id: str) -> bool:
        ...


# ─────────────────────────────────────────────────────────────────────────────
# In-memory fallback
# ─────────────────────────────────────────────────────────────────────────────

class InMemorySessionStore(AbstractSessionStore):
    """
    Thread-safe in-memory session store.

    Used when MongoDB is unavailable.  Not suitable for multi-process
    deployments (HF Spaces free tier = single process, so it works fine).
    """

    def __init__(self, max_sessions: int = 1000) -> None:
        self._sessions: dict[str, dict] = {}
        self._max = max_sessions

    async def create_session(
        self,
        birth_data: dict[str, Any],
        chart_id: str,
    ) -> str:
        # Evict oldest sessions if at capacity
        if len(self._sessions) >= self._max:
            oldest = min(self._sessions, key=lambda k: self._sessions[k]["created_at"])
            del self._sessions[oldest]

        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "_id": session_id,
            "created_at": _now(),
            "updated_at": _now(),
            "birth_data": birth_data,
            "chart_id": chart_id,
            "queries": [],
        }
        return session_id

    async def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        return self._sessions.get(session_id)

    async def add_query(
        self,
        session_id: str,
        query: str,
        domain: str,
        reading_summary: str,
        score: float,
        interpretation: str,
        was_revised: bool,
    ) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        session["queries"].append({
            "query": query,
            "domain": domain,
            "reading_summary": reading_summary[:400],
            "score": round(score, 3),
            "interpretation": interpretation,
            "was_revised": was_revised,
            "timestamp": _now(),
        })
        session["updated_at"] = _now()

    async def get_history(self, session_id: str) -> list[dict[str, Any]]:
        session = self._sessions.get(session_id)
        return session["queries"] if session else []

    async def session_exists(self, session_id: str) -> bool:
        return session_id in self._sessions


# ─────────────────────────────────────────────────────────────────────────────
# MongoDB implementation
# ─────────────────────────────────────────────────────────────────────────────

class MongoSessionStore(AbstractSessionStore):
    """
    MongoDB-backed session store.

    Uses the ``sessions`` collection in the configured database.
    TTL index on ``updated_at`` (90 days) prevents unbounded growth.
    """

    _COLLECTION = "sessions"
    _TTL_DAYS   = 90

    def __init__(self) -> None:
        self._col = None

    async def _get_col(self):
        if self._col is None:
            from vedic_astro.storage.mongo_client import get_mongo_db
            db = await get_mongo_db()
            self._col = db[self._COLLECTION]
            # Ensure TTL index exists (idempotent)
            try:
                await self._col.create_index(
                    "updated_at",
                    expireAfterSeconds=self._TTL_DAYS * 86400,
                    background=True,
                )
            except Exception:
                pass
        return self._col

    async def create_session(
        self,
        birth_data: dict[str, Any],
        chart_id: str,
    ) -> str:
        col = await self._get_col()
        session_id = str(uuid.uuid4())
        await col.insert_one({
            "_id": session_id,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "birth_data": birth_data,
            "chart_id": chart_id,
            "queries": [],
        })
        return session_id

    async def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        col = await self._get_col()
        return await col.find_one({"_id": session_id})

    async def add_query(
        self,
        session_id: str,
        query: str,
        domain: str,
        reading_summary: str,
        score: float,
        interpretation: str,
        was_revised: bool,
    ) -> None:
        col = await self._get_col()
        await col.update_one(
            {"_id": session_id},
            {
                "$push": {"queries": {
                    "query": query,
                    "domain": domain,
                    "reading_summary": reading_summary[:400],
                    "score": round(score, 3),
                    "interpretation": interpretation,
                    "was_revised": was_revised,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
            upsert=False,
        )

    async def get_history(self, session_id: str) -> list[dict[str, Any]]:
        session = await self.get_session(session_id)
        return session.get("queries", []) if session else []

    async def session_exists(self, session_id: str) -> bool:
        col = await self._get_col()
        count = await col.count_documents({"_id": session_id}, limit=1)
        return count > 0


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────

_store_instance: Optional[AbstractSessionStore] = None


class SessionStoreFactory:
    """Auto-select MongoDB or in-memory based on connectivity."""

    @staticmethod
    async def create() -> AbstractSessionStore:
        """
        Return a working session store.

        Tries MongoDB first; falls back silently to in-memory.
        """
        global _store_instance
        if _store_instance is not None:
            return _store_instance

        try:
            store = MongoSessionStore()
            await store._get_col()   # ping
            _store_instance = store
            logger.info("SessionStore: using MongoDB")
        except Exception as exc:
            logger.warning("MongoDB unavailable (%s) — using in-memory session store", exc)
            _store_instance = InMemorySessionStore()

        return _store_instance


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
