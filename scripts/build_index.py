#!/usr/bin/env python3
"""
build_index.py — Build FAISS indexes for rules and cases.

Builds two separate indexes:
1. **Rules index** (``data/embeddings/rules``):
   Embeds structured rules extracted from classical texts.
   Source: ``data/processed/rules.json``

2. **Cases index** (``data/embeddings/cases``):
   Embeds VedAstro case summaries for similarity retrieval.
   Source: ``data/raw/vedastro/cases.json``

Each index is only rebuilt if the source data has changed
(checksum-based staleness detection via VectorStore).

Run with:
    make build-index
    uv run python scripts/build_index.py [--rules-only] [--cases-only] [--force]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


RULES_JSON   = Path("data/processed/rules.json")
RULES_INDEX  = Path("data/embeddings/rules")
CASES_JSON   = Path("data/raw/vedastro/cases.json")
CASES_INDEX  = Path("data/embeddings/cases")


def load_embedder():
    try:
        from vedic_astro.rag.embedder import get_embedder
        return get_embedder()
    except ImportError as exc:
        logger.error("sentence-transformers not installed: %s", exc)
        logger.error("Run: pip install sentence-transformers")
        sys.exit(1)


def build_rules_index(embedder, force: bool = False) -> None:
    """Build FAISS index from extracted rules JSON."""
    if not RULES_JSON.exists():
        logger.warning("Rules file not found: %s — run 'make ingest-rules' first", RULES_JSON)
        return

    with open(RULES_JSON, encoding="utf-8") as f:
        rules = json.load(f)

    if not rules:
        logger.warning("No rules to index")
        return

    from vedic_astro.rag.vector_store import VectorStore
    store = VectorStore(RULES_INDEX)

    source_hash = VectorStore.compute_source_hash([RULES_JSON])
    if not force and not store.is_stale(source_hash):
        logger.info("Rules index is up to date (%d vectors) — skipping", store.size)
        return

    texts = [r.get("text", r.get("condition", "") + " " + r.get("outcome", "")).strip()
             for r in rules]
    metadatas = [
        {
            "rule_id": r.get("id", r.get("rule_id", "")),
            "source_name": r.get("source", ""),
            "domain": r.get("domain", "natal"),
            "polarity": r.get("polarity", "neutral"),
        }
        for r in rules
    ]

    store.build(texts, metadatas, embedder, source_hash=source_hash, show_progress=True)
    store.save()
    logger.info("Rules index built: %d vectors at %s", store.size, RULES_INDEX)


def build_cases_index(embedder, force: bool = False) -> None:
    """Build FAISS index from VedAstro case summaries."""
    if not CASES_JSON.exists():
        logger.warning("Cases file not found: %s — run 'make ingest-cases' first", CASES_JSON)
        return

    with open(CASES_JSON, encoding="utf-8") as f:
        cases = json.load(f)

    if not cases:
        logger.warning("No cases to index")
        return

    from vedic_astro.rag.vector_store import VectorStore
    store = VectorStore(CASES_INDEX)

    source_hash = VectorStore.compute_source_hash([CASES_JSON])
    if not force and not store.is_stale(source_hash):
        logger.info("Cases index is up to date (%d vectors) — skipping", store.size)
        return

    texts = [c.get("summary") or c.get("notes", "")[:500] for c in cases]
    metadatas = [
        {
            "case_id": c.get("case_id", ""),
            "name": c.get("name", ""),
            "lagna_sign": c.get("lagna_sign"),
            "moon_sign": c.get("moon_sign"),
            "maha_lord": c.get("maha_lord"),
            "tags": c.get("tags", []),
        }
        for c in cases
    ]

    store.build(texts, metadatas, embedder, source_hash=source_hash, show_progress=True)
    store.save()
    logger.info("Cases index built: %d vectors at %s", store.size, CASES_INDEX)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build FAISS indexes")
    parser.add_argument("--rules-only", action="store_true")
    parser.add_argument("--cases-only", action="store_true")
    parser.add_argument("--force", action="store_true", help="Rebuild even if index is current")
    args = parser.parse_args()

    embedder = load_embedder()

    if not args.cases_only:
        build_rules_index(embedder, force=args.force)

    if not args.rules_only:
        build_cases_index(embedder, force=args.force)

    logger.info("Done.")


if __name__ == "__main__":
    main()
