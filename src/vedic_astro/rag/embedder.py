"""
embedder.py — Text embedding via Anthropic or sentence-transformers fallback.

Strategy
--------
- Primary: ``sentence-transformers/all-MiniLM-L6-v2`` (local, free, fast).
  384-dimensional embeddings; suitable for cosine similarity search.
- Fallback: dummy zero-vector (so tests run without any model installed).

Embeddings are cached in Redis (7-day TTL) keyed by sha256(text).

Usage
-----
    from vedic_astro.rag.embedder import get_embedder
    embedder = get_embedder()
    vec = await embedder.embed("Jupiter in the 9th house gives fortune")
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_DIM = 384  # all-MiniLM-L6-v2 dimension


class Embedder:
    """Local sentence-transformer embedder with Redis caching."""

    def __init__(self) -> None:
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore[import]
                self._model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("Embedder: loaded all-MiniLM-L6-v2")
            except ImportError:
                logger.warning(
                    "sentence-transformers not installed — using dummy embeddings. "
                    "Run: pip install sentence-transformers"
                )
                self._model = "dummy"
        return self._model

    async def embed(self, text: str) -> np.ndarray:
        """
        Embed a single text string.

        Returns
        -------
        np.ndarray
            Shape (384,), dtype float32.
        """
        from vedic_astro.tools.hasher import _sha256_short
        from vedic_astro.tools.cache import get_cache
        from vedic_astro.settings import settings

        cache_key = f"va:embed:{_sha256_short(text, 32)}"
        cache = get_cache()

        cached = await cache.get(cache_key)
        if cached is not None:
            return np.array(cached, dtype=np.float32)

        vec = self._compute(text)

        await cache.set(cache_key, vec.tolist(), ttl=settings.cache_llm_response_ttl)
        return vec

    async def embed_batch(self, texts: list[str]) -> np.ndarray:
        """
        Embed multiple texts.

        Returns
        -------
        np.ndarray
            Shape (N, 384), dtype float32.
        """
        vecs = [await self.embed(t) for t in texts]
        return np.stack(vecs, axis=0)

    def encode_texts_sync(
        self,
        texts: list[str],
        batch_size: int = 64,
        show_progress: bool = False,
    ) -> np.ndarray:
        """
        Synchronous bulk encoding for offline index-building pipelines.

        Bypasses Redis cache — returns raw numpy array directly.
        Uses sentence-transformers batch encode for maximum throughput.

        Parameters
        ----------
        texts         : List of strings to encode.
        batch_size    : Encoding batch size (tune for available VRAM/RAM).
        show_progress : Display tqdm progress bar.

        Returns
        -------
        np.ndarray
            Shape (N, 384), dtype float32, L2-normalised.
        """
        model = self._load_model()
        if model == "dummy":
            return np.zeros((len(texts), _DIM), dtype=np.float32)
        matrix = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
        )
        return matrix.astype(np.float32)

    def _compute(self, text: str) -> np.ndarray:
        model = self._load_model()
        if model == "dummy":
            return np.zeros(_DIM, dtype=np.float32)
        vec = model.encode(text, normalize_embeddings=True)
        return vec.astype(np.float32)


_embedder_instance: Optional[Embedder] = None


def get_embedder() -> Embedder:
    """Return the application-wide Embedder singleton."""
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = Embedder()
    return _embedder_instance
