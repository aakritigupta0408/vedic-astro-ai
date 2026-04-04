"""
rule_retriever.py — Classical rule retrieval from the FAISS vector store.

Retrieval strategy
------------------
1. Embed the query with ``sentence-transformers/all-MiniLM-L6-v2``.
2. Search the persisted FAISS index (built by ``scripts/build_index.py``).
3. Return the top-k ``SearchResult.formatted`` strings, ordered by
   cosine similarity descending.

The index is loaded lazily on first call and kept in memory for the
lifetime of the process.  Rebuilding the index does not require restarting
the application — call ``RuleRetriever.reload()`` to force a fresh load.

Query augmentation
------------------
The raw user query is too short for reliable embedding retrieval.
``_augment_query`` prepends domain keywords so the embedding is
anchored in the correct subdomain (natal / dasha / transit / divisional).

Usage
-----
    retriever = RuleRetriever()
    rules = await retriever.retrieve("Jupiter dasha career", top_k=5)
    # ["Jupiter in 10th gives professional success [BPHS]", ...]
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from vedic_astro.rag.vector_store import VectorStore
from vedic_astro.settings import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Query augmentation helpers
# ─────────────────────────────────────────────────────────────────────────────

_DOMAIN_PREFIXES: dict[str, str] = {
    "dasha":      "Vimshottari dasha period lord timing prediction",
    "transit":    "gochara transit planet movement over natal chart",
    "divisional": "varga divisional navamsha D9 dashamsha D10 chart",
    "yoga":       "planetary yoga combination conjunction strong placement",
    "dosha":      "planetary affliction dosha weakness debilitation",
    "panchang":   "tithi nakshatra vara yoga karana panchang",
}

_DOMAIN_TRIGGERS: dict[str, list[str]] = {
    "dasha":      ["dasha", "antardasha", "maha dasha", "period", "timing"],
    "transit":    ["transit", "gochara", "transiting"],
    "divisional": ["navamsha", "d9", "d10", "varga", "divisional"],
    "yoga":       ["yoga", "raj yoga", "mahapurusha", "dhana yoga"],
    "dosha":      ["dosha", "mangal", "kala sarpa", "kemdrum"],
    "panchang":   ["tithi", "nakshatra", "vara", "panchang"],
}


def _detect_domain(query: str) -> str:
    ql = query.lower()
    for domain, triggers in _DOMAIN_TRIGGERS.items():
        if any(t in ql for t in triggers):
            return domain
    return "natal"


def _augment_query(query: str) -> str:
    """Prepend domain keywords to improve retrieval relevance."""
    domain = _detect_domain(query)
    prefix = _DOMAIN_PREFIXES.get(domain, "Vedic astrology natal chart planet house")
    return f"{prefix}: {query}"


# ─────────────────────────────────────────────────────────────────────────────
# Retriever
# ─────────────────────────────────────────────────────────────────────────────

class RuleRetriever:
    """FAISS-backed classical rule retriever with query augmentation."""

    def __init__(self, index_base: str | Path | None = None) -> None:
        base = Path(index_base) if index_base else Path(settings.faiss_index_path)
        self._store = VectorStore.load(base)

    async def retrieve(self, query: str, top_k: int = 5) -> list[str]:
        """
        Retrieve classical rules most relevant to *query*.

        Parameters
        ----------
        query   : Natural-language query (e.g. "Jupiter dasha career prospects").
        top_k   : Max rules to return.

        Returns
        -------
        list[str]
            Rule texts with source attribution, ordered by relevance.
        """
        if not self._store.is_ready:
            logger.debug("Rule index not available — returning empty rules")
            return []

        from vedic_astro.rag.embedder import get_embedder
        embedder = get_embedder()

        augmented = _augment_query(query)
        query_vec = await embedder.embed(augmented)

        results = self._store.search(query_vec, k=top_k, min_score=0.15)
        return [r.formatted for r in results]

    def reload(self) -> None:
        """Force reload the FAISS index from disk."""
        self._store._loaded = False
        self._store._index = None
        self._store._metadata = []
        self._store._try_load()

    @property
    def index_size(self) -> int:
        return self._store.size


# ─────────────────────────────────────────────────────────────────────────────
# Domain-filtered retrieval (used by agents for targeted rule lookup)
# ─────────────────────────────────────────────────────────────────────────────

async def retrieve_rules_for_domain(
    query: str,
    domain: str,
    top_k: int = 5,
) -> list[str]:
    """
    Retrieve rules filtered to a specific domain.

    Injects the domain into the query string so the embedding is anchored
    in the correct subdomain.

    Parameters
    ----------
    query   : User question or agent context string.
    domain  : "natal" | "dasha" | "transit" | "divisional" | "yoga" | "dosha"
    top_k   : Number of results.

    Returns
    -------
    list[str]
        Rule texts with source attribution.
    """
    prefix = _DOMAIN_PREFIXES.get(domain, "")
    augmented_query = f"{prefix} {query}".strip()
    retriever = RuleRetriever()
    return await retriever.retrieve(augmented_query, top_k=top_k)
