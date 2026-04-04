#!/usr/bin/env python3
"""
extract_rules.py — Extract structured rules from classical astrology texts.

Pipeline
--------
1. Load all ``.txt`` / ``.pdf`` files from ``data/raw/texts/``.
2. Chunk them with ``SmartChunker`` (verse-aware then sliding-window fallback).
3. For each chunk, run ``RuleExtractor`` (LLM extraction with regex fallback).
4. Deduplicate by rule_id and save to ``data/processed/rules.json``.

The extraction step caches results per chunk in Redis so re-runs only
process new or changed chunks.  Pass ``--no-llm`` to skip LLM and use
regex-only extraction (useful offline or when API key is not set).

Run with:
    make ingest-rules
    uv run python scripts/extract_rules.py [--no-llm] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RAW_DIR   = Path("data/raw/texts")
OUT_PATH  = Path("data/processed/rules.json")


async def main(use_llm: bool = True, limit: int = 0, concurrency: int = 6) -> None:
    from vedic_astro.rag.loaders import DirectoryLoader
    from vedic_astro.rag.chunker import SmartChunker
    from vedic_astro.rag.rule_extractor import RuleExtractor

    # ── 1. Load documents ─────────────────────────────────────────────────
    if not RAW_DIR.exists():
        logger.warning("Text directory not found: %s", RAW_DIR)
        logger.warning("Place classical text files (*.txt / *.pdf) in data/raw/texts/")
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text("[]")
        return

    docs = DirectoryLoader(RAW_DIR).load()
    if not docs:
        logger.warning("No documents found in %s", RAW_DIR)
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text("[]")
        return

    logger.info("Loaded %d documents", len(docs))

    # ── 2. Chunk ──────────────────────────────────────────────────────────
    chunks = SmartChunker().chunk(docs)
    logger.info("Chunked into %d chunks", len(chunks))

    if limit > 0:
        chunks = chunks[:limit]
        logger.info("Limited to %d chunks", len(chunks))

    # ── 3. Extract rules ──────────────────────────────────────────────────
    extractor = RuleExtractor(use_llm=use_llm)
    rules = await extractor.extract_batch(chunks, concurrency=concurrency)

    # ── 4. Merge with any existing rules (for incremental runs) ──────────
    existing: list[dict] = []
    if OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            existing = []

    existing_ids = {r.get("rule_id") for r in existing}
    new_rules = [r.model_dump() for r in rules if r.rule_id not in existing_ids]
    all_rules = existing + new_rules

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(all_rules, indent=2, ensure_ascii=False))
    logger.info(
        "Saved %d rules (%d new, %d existing) → %s",
        len(all_rules), len(new_rules), len(existing), OUT_PATH,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm", action="store_true", help="Use regex-only extraction")
    parser.add_argument("--limit", type=int, default=0, help="Max chunks to process (0=all)")
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()

    asyncio.run(main(
        use_llm=not args.no_llm,
        limit=args.limit,
        concurrency=args.concurrency,
    ))
