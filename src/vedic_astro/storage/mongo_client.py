"""
mongo_client.py — Async MongoDB client singleton via Motor.

Collections
-----------
charts      : Serialised NatalChart documents, keyed by chart_id.
reports     : Final LLM reading outputs, keyed by (chart_id, query_hash).
rules       : Classical shastra rules extracted from texts.
cases       : VedAstro reference cases used for RAG retrieval.
feedback    : User ratings/corrections for RL-style rule weighting.

Usage
-----
    db = await get_mongo_db()
    doc = await db["charts"].find_one({"_id": chart_id})
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_db_instance = None


async def get_mongo_db():
    """
    Return the application-wide Motor AsyncIOMotorDatabase.

    Connects on first call; subsequent calls return the cached handle.
    The connection is not explicitly closed — Motor handles pooling.
    """
    global _db_instance
    if _db_instance is not None:
        return _db_instance

    try:
        import motor.motor_asyncio as motor  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "motor package not installed. Run: pip install motor"
        ) from exc

    from vedic_astro.settings import settings

    client = motor.AsyncIOMotorClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
    )
    # Ping to verify connection
    try:
        await client.admin.command("ping")
        logger.info("MongoDB connected: %s", settings.mongodb_uri)
    except Exception as exc:
        logger.error("MongoDB connection failed: %s", exc)
        raise RuntimeError(f"Cannot connect to MongoDB: {exc}") from exc

    _db_instance = client[settings.mongodb_database]
    return _db_instance
