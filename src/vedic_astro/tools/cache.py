"""
cache.py — Redis cache client with typed get/set/delete and TTL helpers.

Design
------
- Thin wrapper around ``redis.asyncio`` (async-first) with a sync fallback.
- All values are serialised as JSON so they survive Redis restarts.
- TTL=0 means *permanent* (no expiry), matching the settings convention.
- A ``NullCache`` is returned when Redis is unavailable so the rest of
  the application degrades gracefully.

Usage
-----
    from vedic_astro.tools.cache import get_cache

    cache = get_cache()
    await cache.set("va:natal:abc123", chart.model_dump(), ttl=0)
    data = await cache.get("va:natal:abc123")
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Abstract base
# ─────────────────────────────────────────────────────────────────────────────

class CacheClient:
    """
    Async cache client backed by Redis.

    All methods are coroutines.  Use ``get_cache()`` to obtain a singleton.
    """

    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        self._client: Any = None
        self._unavailable: bool = False   # set on first failure; suppresses repeat warnings

    async def _ensure_connected(self) -> bool:
        if self._client is not None:
            return True
        if self._unavailable:
            return False
        try:
            import redis.asyncio as aioredis  # type: ignore[import]
            self._client = aioredis.from_url(
                self._url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await self._client.ping()
            logger.debug("Redis connected: %s", self._url)
            return True
        except Exception as exc:
            logger.warning("Redis unavailable (%s) — caching disabled", exc)
            self._client = None
            self._unavailable = True
            return False

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a cached value by *key*.

        Returns the deserialised Python object, or ``None`` on miss / error.
        """
        if not await self._ensure_connected():
            return None
        try:
            raw = await self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.debug("Cache GET error for key %r: %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: int = 86400) -> bool:
        """
        Store *value* at *key*.

        Parameters
        ----------
        key   : Redis key string.
        value : JSON-serialisable Python object.
        ttl   : Seconds until expiry.  ``0`` means permanent (no EXPIRE set).

        Returns
        -------
        bool
            ``True`` on success, ``False`` on error / no connection.
        """
        if not await self._ensure_connected():
            return False
        try:
            serialised = json.dumps(value, default=str)
            if ttl == 0:
                await self._client.set(key, serialised)
            else:
                await self._client.setex(key, ttl, serialised)
            return True
        except Exception as exc:
            logger.warning("Cache SET error for key %r: %s", key, exc)
            return False

    async def delete(self, key: str) -> bool:
        """Delete a single *key*.  Returns ``True`` if the key existed."""
        if not await self._ensure_connected():
            return False
        try:
            result = await self._client.delete(key)
            return result > 0
        except Exception as exc:
            logger.warning("Cache DELETE error for key %r: %s", key, exc)
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching *pattern* (e.g. ``va:natal:*``).

        Uses SCAN + batch DELETE to avoid blocking Redis.

        Returns
        -------
        int
            Number of keys deleted.
        """
        if not await self._ensure_connected():
            return 0
        deleted = 0
        try:
            async for key in self._client.scan_iter(match=pattern, count=100):
                await self._client.delete(key)
                deleted += 1
        except Exception as exc:
            logger.warning("Cache DELETE pattern %r error: %s", pattern, exc)
        return deleted

    async def exists(self, key: str) -> bool:
        """Return ``True`` if *key* exists in Redis."""
        if not await self._ensure_connected():
            return False
        try:
            return bool(await self._client.exists(key))
        except Exception as exc:
            logger.warning("Cache EXISTS error for key %r: %s", key, exc)
            return False

    async def ttl(self, key: str) -> int:
        """
        Return remaining TTL in seconds.

        Special return values (Redis semantics):
        * ``-1`` → key exists but has no expiry (permanent).
        * ``-2`` → key does not exist.
        """
        if not await self._ensure_connected():
            return -2
        try:
            return await self._client.ttl(key)
        except Exception as exc:
            logger.warning("Cache TTL error for key %r: %s", key, exc)
            return -2

    async def close(self) -> None:
        """Close the underlying Redis connection."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# ─────────────────────────────────────────────────────────────────────────────
# Singleton factory
# ─────────────────────────────────────────────────────────────────────────────

_cache_instance: Optional[CacheClient] = None


def get_redis():
    """Return a synchronous Redis client, or raise if unavailable."""
    import redis as _redis
    from vedic_astro.settings import settings
    client = _redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    client.ping()
    return client


def get_cache(redis_url: Optional[str] = None) -> CacheClient:
    """
    Return the application-wide CacheClient singleton.

    On the first call the *redis_url* is read from ``settings`` if not
    provided explicitly.  Subsequent calls ignore *redis_url*.
    """
    global _cache_instance
    if _cache_instance is None:
        if redis_url is None:
            from vedic_astro.settings import settings
            redis_url = settings.redis_url
        _cache_instance = CacheClient(redis_url)
    return _cache_instance


# ─────────────────────────────────────────────────────────────────────────────
# Decorator helpers for engine functions
# ─────────────────────────────────────────────────────────────────────────────

def _sync_get(key: str) -> Optional[Any]:
    """
    Synchronous cache GET via a new event loop.

    Used by ``@cache_natal`` and ``@cache_panchang`` decorators so the
    engine functions do not need to be async themselves.
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Inside an async context — schedule and await
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(
                get_cache().get(key), loop
            )
            return future.result(timeout=2)
        else:
            return loop.run_until_complete(get_cache().get(key))
    except Exception:
        return None


def _sync_set(key: str, value: Any, ttl: int) -> None:
    """Synchronous cache SET — mirrors ``_sync_get``."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(
                get_cache().set(key, value, ttl=ttl), loop
            )
            future.result(timeout=2)
        else:
            loop.run_until_complete(get_cache().set(key, value, ttl=ttl))
    except Exception:
        pass


def cache_natal(key_fn):
    """
    Decorator factory for permanent natal-chart caching.

    Usage::

        @cache_natal(lambda *a, **kw: make_natal_key(...))
        def build_natal_chart(...) -> NatalChart: ...

    The wrapped function must return a Pydantic model with ``.model_dump()``
    / ``.model_validate()``, or a dataclass with ``asdict()`` support.
    """
    import functools

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            from vedic_astro.settings import settings
            key = key_fn(*args, **kwargs)
            cached = _sync_get(key)
            if cached is not None:
                # Reconstruct from dict using the return annotation
                import typing, inspect
                hints = typing.get_type_hints(fn)
                ret_type = hints.get("return")
                if ret_type is not None and hasattr(ret_type, "model_validate"):
                    return ret_type.model_validate(cached)
                return cached  # plain dict fallback
            result = fn(*args, **kwargs)
            data = result.model_dump() if hasattr(result, "model_dump") else result
            _sync_set(key, data, ttl=settings.cache_natal_ttl)
            return result
        return wrapper
    return decorator
