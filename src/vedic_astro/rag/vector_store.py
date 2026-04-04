"""
vector_store.py — FAISS-backed vector store with disk persistence.

Architecture
------------
Each index lives in two files:

    <name>.index          FAISS binary index (IndexFlatIP for cosine similarity
                          on L2-normalised vectors)
    <name>.meta.json      JSON sidecar: list of {text, metadata} dicts, one per vector
    <name>.checksum       SHA256 of the source data used to build the index

The checksum allows ``is_stale(source_hash)`` to return True if the source
data has changed since the index was built — triggering a rebuild.

Two index variants are supported:
    flat   (default, <100k vectors)  : IndexFlatIP — exact search, no training
    ivf    (>100k vectors)           : IndexIVFFlat — approximate, 10–100× faster

Usage
-----
    store = VectorStore(Path("data/embeddings/rules"))
    store.build(texts, metadatas, embedder)
    store.save()

    # later
    store = VectorStore.load(Path("data/embeddings/rules"))
    results = store.search(query_vec, k=5)
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# FAISS IVF nlist heuristic: sqrt(n_vectors), capped at 256 for small datasets
_IVF_THRESHOLD = 10_000    # use IVF above this many vectors
_IVF_NLIST_MAX = 256


# ─────────────────────────────────────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SearchResult:
    """A single retrieval result with relevance score."""
    text: str
    metadata: dict
    score: float          # cosine similarity (0–1 for normalised vecs)
    rank: int

    @property
    def source(self) -> str:
        return self.metadata.get("source_name", self.metadata.get("source", ""))

    @property
    def formatted(self) -> str:
        """Text with source attribution, suitable for LLM prompts."""
        src = self.source
        return f"{self.text} [{src}]" if src else self.text


# ─────────────────────────────────────────────────────────────────────────────
# Vector store
# ─────────────────────────────────────────────────────────────────────────────

class VectorStore:
    """
    FAISS vector store with disk persistence and staleness detection.

    Parameters
    ----------
    base_path : Path prefix (without extension). Files created:
                ``{base_path}.index``, ``{base_path}.meta.json``,
                ``{base_path}.checksum``
    """

    def __init__(self, base_path: Path | str) -> None:
        self._base = Path(base_path)
        self._index_path = self._base.with_suffix(".index")
        self._meta_path  = self._base.with_suffix(".meta.json")
        self._csum_path  = self._base.with_suffix(".checksum")

        self._index = None          # faiss.Index | None
        self._metadata: list[dict] = []
        self._loaded = False

    # ── Build ──────────────────────────────────────────────────────────────

    def build(
        self,
        texts: list[str],
        metadatas: list[dict],
        embedder,
        source_hash: str = "",
        batch_size: int = 64,
        show_progress: bool = True,
    ) -> None:
        """
        Encode texts and build a new FAISS index in memory.

        Parameters
        ----------
        texts       : Raw text strings.
        metadatas   : One dict per text (same order).
        embedder    : ``Embedder`` instance for ``encode_texts_sync()``.
        source_hash : SHA256 of source data — stored for staleness checks.
        batch_size  : Embedding batch size.
        show_progress : Show tqdm progress bar.
        """
        if len(texts) != len(metadatas):
            raise ValueError("texts and metadatas must have the same length")
        if not texts:
            raise ValueError("Cannot build an empty index")

        try:
            import faiss  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("faiss-cpu not installed. Run: pip install faiss-cpu") from exc

        logger.info("Building FAISS index for %d documents...", len(texts))
        matrix = embedder.encode_texts_sync(texts, batch_size=batch_size, show_progress=show_progress)
        dim = matrix.shape[1]
        n   = matrix.shape[0]

        if n >= _IVF_THRESHOLD:
            nlist = min(int(n ** 0.5), _IVF_NLIST_MAX)
            quantizer = faiss.IndexFlatIP(dim)
            index = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)
            index.train(matrix)
            logger.info("IVF index: dim=%d nlist=%d", dim, nlist)
        else:
            index = faiss.IndexFlatIP(dim)
            logger.info("Flat index: dim=%d n=%d", dim, n)

        index.add(matrix)
        self._index = index
        self._metadata = [{"text": t, **m} for t, m in zip(texts, metadatas)]

        self._source_hash = source_hash
        self._loaded = True
        logger.info("FAISS index built: %d vectors", index.ntotal)

    # ── Persistence ────────────────────────────────────────────────────────

    def save(self) -> None:
        """Write index + metadata + checksum to disk."""
        if self._index is None:
            raise RuntimeError("No index to save — call build() first")

        try:
            import faiss  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("faiss-cpu not installed") from exc

        self._base.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self._index_path))

        with open(self._meta_path, "w", encoding="utf-8") as f:
            json.dump(self._metadata, f, ensure_ascii=False)

        self._csum_path.write_text(getattr(self, "_source_hash", ""))
        logger.info("VectorStore saved: %s (%d vectors)", self._index_path, self._index.ntotal)

    @classmethod
    def load(cls, base_path: Path | str) -> "VectorStore":
        """
        Load a persisted VectorStore from disk.

        Returns a ready-to-search store, or an empty store if files
        don't exist (``search()`` returns [] gracefully).
        """
        store = cls(base_path)
        store._try_load()
        return store

    def _try_load(self) -> bool:
        if self._loaded:
            return self._index is not None
        self._loaded = True

        if not self._index_path.exists() or not self._meta_path.exists():
            logger.debug("VectorStore not found at %s", self._index_path)
            return False

        try:
            import faiss  # type: ignore[import]
            self._index = faiss.read_index(str(self._index_path))
            with open(self._meta_path, encoding="utf-8") as f:
                self._metadata = json.load(f)
            logger.info("VectorStore loaded: %d vectors from %s", self._index.ntotal, self._index_path)
            return True
        except Exception as exc:
            logger.warning("VectorStore load error: %s", exc)
            self._index = None
            self._metadata = []
            return False

    # ── Staleness ──────────────────────────────────────────────────────────

    def is_stale(self, source_hash: str) -> bool:
        """
        Return True if the source data has changed since the index was built.

        Parameters
        ----------
        source_hash : SHA256 of the current source data.

        Returns
        -------
        bool
            True → rebuild needed.  False → index is current.
        """
        if not self._csum_path.exists():
            return True
        stored = self._csum_path.read_text().strip()
        return stored != source_hash.strip()

    @staticmethod
    def compute_source_hash(paths: list[Path]) -> str:
        """
        Compute a combined SHA256 checksum over a set of files.

        Used to detect when source text files have changed.
        """
        h = hashlib.sha256()
        for path in sorted(paths):
            if path.exists():
                h.update(path.read_bytes())
        return h.hexdigest()

    # ── Search ─────────────────────────────────────────────────────────────

    def search(
        self,
        query_vec: np.ndarray,
        k: int = 5,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """
        Find the *k* most similar chunks.

        Parameters
        ----------
        query_vec  : 1-D float32 array, L2-normalised.
        k          : Number of results to return.
        min_score  : Minimum cosine similarity to include.

        Returns
        -------
        list[SearchResult]
            Ordered by similarity descending.
        """
        if not self._try_load() or self._index is None:
            return []

        k = min(k, self._index.ntotal)
        if k == 0:
            return []

        qv = np.array(query_vec, dtype=np.float32).reshape(1, -1)
        distances, indices = self._index.search(qv, k)

        results = []
        for rank, (dist, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < 0 or idx >= len(self._metadata):
                continue
            score = float(dist)
            if score < min_score:
                continue
            meta = self._metadata[idx]
            text = meta.pop("text", "")
            results.append(SearchResult(
                text=text,
                metadata=dict(meta),
                score=score,
                rank=rank,
            ))
            meta["text"] = text  # restore (pop was mutable)

        return results

    # ── Diagnostics ────────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        """Number of vectors in the index."""
        if self._index is None:
            self._try_load()
        return self._index.ntotal if self._index is not None else 0

    @property
    def is_ready(self) -> bool:
        """True if the index is loaded and non-empty."""
        return self._try_load() and self._index is not None and self._index.ntotal > 0
