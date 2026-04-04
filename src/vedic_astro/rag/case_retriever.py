"""
case_retriever.py — Feature-aware similar-case retrieval from VedAstro dataset.

Retrieval strategy (hybrid scoring)
------------------------------------
Structural similarity  (60%)  — chart fingerprint matching:
    - Lagna sign match        +25 pts
    - Moon sign match         +20 pts
    - Maha dasha lord match   +15 pts

Semantic similarity    (40%)  — embedding cosine on case summary + query:
    Uses the prebuilt ``cases`` FAISS index.

Query domain filtering:
    Career  → boost cases with "career"/"profession" tags
    Marriage → boost "marriage"/"relationship" tags
    Health  → boost "health"/"disease" tags

The combined score determines ranking.  Only cases with at least one
structural OR semantic match are returned.

Usage
-----
    retriever = CaseRetriever()
    cases = await retriever.retrieve(chart, query, top_k=3)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

from vedic_astro.settings import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Domain → tag map
# ─────────────────────────────────────────────────────────────────────────────

_DOMAIN_TAGS: dict[str, list[str]] = {
    "career":       ["career", "profession", "job", "business", "success"],
    "marriage":     ["marriage", "relationship", "spouse", "divorce"],
    "health":       ["health", "disease", "surgery", "illness", "accident"],
    "wealth":       ["wealth", "finance", "money", "poverty", "riches"],
    "spirituality": ["spiritual", "meditation", "religion", "yoga"],
    "children":     ["children", "fertility", "childbirth"],
}


def _detect_query_domain(query: str) -> Optional[str]:
    ql = query.lower()
    for domain, tags in _DOMAIN_TAGS.items():
        if any(t in ql for t in tags):
            return domain
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Scored case
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScoredCase:
    record: dict[str, Any]
    structural_score: float
    semantic_score: float
    domain_bonus: float

    @property
    def total_score(self) -> float:
        return 0.60 * self.structural_score + 0.40 * self.semantic_score + self.domain_bonus


# ─────────────────────────────────────────────────────────────────────────────
# Retriever
# ─────────────────────────────────────────────────────────────────────────────

class CaseRetriever:
    """
    Hybrid structural + semantic similar-case retriever.

    The cases FAISS index is built separately from the rules index
    (``scripts/build_case_index.py``).  If the index doesn't exist,
    falls back to structural-only matching over the JSON case file.
    """

    def __init__(
        self,
        cases_path: str | Path | None = None,
        index_base: str | Path | None = None,
    ) -> None:
        data_dir = Path(settings.vedastro_data_path)
        self._cases_path = Path(cases_path) if cases_path else data_dir / "cases.json"
        self._index_base = Path(index_base) if index_base else data_dir / "cases_index"

        self._cases: list[dict] = []
        self._loaded = False

        # Lazy-load FAISS index for semantic matching
        from vedic_astro.rag.vector_store import VectorStore
        self._store = VectorStore.load(self._index_base)

    # ── Public API ────────────────────────────────────────────────────────

    async def retrieve(
        self,
        chart,                   # NatalChart
        query: str,
        top_k: int = 3,
        maha_lord: Optional[str] = None,
    ) -> list[str]:
        """
        Find similar reference cases.

        Parameters
        ----------
        chart     : NatalChart (for structural matching).
        query     : User query (for semantic matching + domain filtering).
        top_k     : Number of cases to return.
        maha_lord : Active Maha dasha lord (for dasha-based matching).

        Returns
        -------
        list[str]
            Case summaries ordered by relevance (for LLM prompt injection).
        """
        self._ensure_loaded()
        if not self._cases:
            return []

        from vedic_astro.engines.natal_engine import PlanetName

        lagna_sign = chart.lagna_sign
        moon_sign  = chart.planets[PlanetName.MOON].sign_number
        query_domain = _detect_query_domain(query)

        # Semantic query vector
        sem_vector = await self._get_query_vector(query)

        scored = []
        for case in self._cases:
            struct = self._structural_score(case, lagna_sign, moon_sign, maha_lord)
            sem    = self._semantic_score(case, sem_vector)
            bonus  = self._domain_bonus(case, query_domain)

            sc = ScoredCase(
                record=case,
                structural_score=struct,
                semantic_score=sem,
                domain_bonus=bonus,
            )
            if sc.total_score > 0.05:
                scored.append(sc)

        scored.sort(key=lambda x: x.total_score, reverse=True)
        return [self._format_case(sc.record) for sc in scored[:top_k]]

    # ── Scoring components ────────────────────────────────────────────────

    @staticmethod
    def _structural_score(
        case: dict,
        lagna_sign: int,
        moon_sign: int,
        maha_lord: Optional[str],
    ) -> float:
        score = 0.0
        if case.get("lagna_sign") == lagna_sign:
            score += 0.40
        if case.get("moon_sign") == moon_sign:
            score += 0.35
        if maha_lord and case.get("maha_lord") == maha_lord:
            score += 0.25
        return min(score, 1.0)

    def _semantic_score(self, case: dict, query_vec: Optional[np.ndarray]) -> float:
        """Cosine similarity between query and case embedding from FAISS."""
        if query_vec is None or not self._store.is_ready:
            return 0.0

        # Case index uses case_id as metadata — look up by matching summary embedding
        # The FAISS index for cases is built with summaries as texts.
        # We search and match by case_id in metadata.
        results = self._store.search(query_vec, k=20)
        for r in results:
            if r.metadata.get("case_id") == case.get("case_id"):
                return float(r.score)
        return 0.0

    @staticmethod
    def _domain_bonus(case: dict, query_domain: Optional[str]) -> float:
        if not query_domain:
            return 0.0
        tags = [t.lower() for t in case.get("tags", [])]
        domain_tags = _DOMAIN_TAGS.get(query_domain, [])
        if any(t in tags for t in domain_tags):
            return 0.10
        # Check notes
        notes = case.get("notes", "").lower()
        if any(t in notes for t in domain_tags):
            return 0.05
        return 0.0

    # ── Helpers ───────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._cases_path.exists():
            logger.info("Cases file not found: %s", self._cases_path)
            return
        try:
            with open(self._cases_path, encoding="utf-8") as f:
                self._cases = json.load(f)
            logger.info("CaseRetriever: loaded %d cases", len(self._cases))
        except Exception as exc:
            logger.warning("Case load error: %s", exc)

    async def _get_query_vector(self, query: str) -> Optional[np.ndarray]:
        try:
            from vedic_astro.rag.embedder import get_embedder
            return await get_embedder().embed(query)
        except Exception:
            return None

    @staticmethod
    def _format_case(case: dict) -> str:
        """Format a case record for injection into an LLM prompt."""
        summary = case.get("summary", "")
        if summary:
            return summary
        name   = case.get("name", "Unknown")
        year   = case.get("year", "")
        notes  = (case.get("notes", "") or "")[:150]
        return f"{name} ({year}): {notes}".strip()


# ─────────────────────────────────────────────────────────────────────────────
# Case FAISS index builder (called from scripts/)
# ─────────────────────────────────────────────────────────────────────────────

async def build_case_index(
    cases_path: Path,
    index_base: Path,
    embedder=None,
) -> None:
    """
    Build and save a FAISS index for case summaries.

    Called by ``scripts/build_index.py``.

    Parameters
    ----------
    cases_path : Path to ``cases.json``.
    index_base : Output path prefix for the FAISS store files.
    embedder   : Embedder instance (or None to use singleton).
    """
    if not cases_path.exists():
        logger.warning("Cases file not found: %s", cases_path)
        return

    with open(cases_path, encoding="utf-8") as f:
        cases = json.load(f)

    if not cases:
        logger.warning("No cases to index")
        return

    if embedder is None:
        from vedic_astro.rag.embedder import get_embedder
        embedder = get_embedder()

    texts     = [c.get("summary", c.get("notes", ""))[:500] for c in cases]
    metadatas = [{"case_id": c.get("case_id", ""), "name": c.get("name", "")} for c in cases]

    source_hash = VectorStore.compute_source_hash([cases_path])

    from vedic_astro.rag.vector_store import VectorStore
    store = VectorStore(index_base)
    store.build(texts, metadatas, embedder, source_hash=source_hash)
    store.save()
    logger.info("Case index built: %d cases at %s", len(cases), index_base)
