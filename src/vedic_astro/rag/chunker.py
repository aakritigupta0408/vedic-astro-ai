"""
chunker.py — Text chunking strategies for classical astrology texts.

Classical texts have distinct structure:
- Numbered verses/shlokas (``1. Jupiter in the 9th house...``)
- Chapter sections with headings
- Dense prose paragraphs

``SmartChunker`` tries verse-aware splitting first.  If the text lacks
verse structure, it falls back to sliding-window chunking with overlap.

Each ``Chunk`` carries a deterministic ``chunk_id`` (sha256 of text + source)
so the same chunk produces the same embedding regardless of re-ingestion order.

Usage
-----
    from vedic_astro.rag.chunker import SmartChunker
    from vedic_astro.rag.loaders import DirectoryLoader

    docs = DirectoryLoader("data/raw/texts").load()
    chunks = SmartChunker().chunk(docs)
    print(chunks[0].chunk_id, chunks[0].text[:80])
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional

from vedic_astro.rag.loaders import Document


# ─────────────────────────────────────────────────────────────────────────────
# Core data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Chunk:
    """A text chunk ready for embedding."""
    text: str
    chunk_id: str                      # sha256(source + text)[:24]
    metadata: dict = field(default_factory=dict)

    @property
    def source(self) -> str:
        return self.metadata.get("source", "unknown")

    @property
    def source_name(self) -> str:
        return self.metadata.get("source_name", "")

    @property
    def chapter(self) -> Optional[int]:
        return self.metadata.get("chapter")


def _make_chunk_id(source: str, text: str) -> str:
    payload = f"{source}|{text[:200]}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


# ─────────────────────────────────────────────────────────────────────────────
# Verse-aware chunker
# ─────────────────────────────────────────────────────────────────────────────

_VERSE_PATTERNS = [
    re.compile(r"^\d+\.\s+", re.MULTILINE),          # "1. Jupiter..."
    re.compile(r"^Verse\s+\d+", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^Shloka\s+\d+", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\d+\)\s+", re.MULTILINE),          # "1) Mars..."
]

_MIN_VERSE_LEN = 40   # ignore fragments shorter than this


class VerseAwareChunker:
    """
    Splits text on numbered verse/shloka boundaries.

    Joins short verses (< min_chars) with the next verse so that embeddings
    have enough semantic content to retrieve reliably.
    """

    def __init__(
        self,
        min_chars: int = 80,
        max_chars: int = 800,
        join_threshold: int = 120,
    ) -> None:
        self._min = min_chars
        self._max = max_chars
        self._join_threshold = join_threshold   # join if shorter than this

    def can_handle(self, text: str) -> bool:
        """Return True if the text contains detectable verse structure."""
        for pat in _VERSE_PATTERNS:
            matches = list(pat.finditer(text))
            if len(matches) >= 3:
                return True
        return False

    def chunk_text(self, text: str, base_metadata: dict) -> list[Chunk]:
        """Split *text* on verse boundaries."""
        # Find the verse pattern that matches most
        best_pat = None
        best_count = 0
        for pat in _VERSE_PATTERNS:
            count = len(list(pat.finditer(text)))
            if count > best_count:
                best_count = count
                best_pat = pat

        if best_pat is None or best_count < 3:
            return []

        # Split on verse boundaries
        raw_verses = best_pat.split(text)
        raw_verses = [v.strip() for v in raw_verses if v.strip()]

        chunks = []
        buffer = ""

        for verse in raw_verses:
            if len(verse) < _MIN_VERSE_LEN:
                buffer += " " + verse
                continue

            combined = (buffer + " " + verse).strip()
            if len(combined) < self._join_threshold:
                buffer = combined
            else:
                if buffer:
                    # flush buffer as separate chunk
                    chunk_text = buffer.strip()
                    if len(chunk_text) >= self._min:
                        chunks.append(self._make_chunk(chunk_text, base_metadata))
                buffer = verse

        if buffer.strip() and len(buffer.strip()) >= self._min:
            chunks.append(self._make_chunk(buffer.strip(), base_metadata))

        return chunks

    def _make_chunk(self, text: str, meta: dict) -> Chunk:
        # Cap at max_chars
        if len(text) > self._max:
            text = text[: self._max].rsplit(" ", 1)[0]
        return Chunk(
            text=text,
            chunk_id=_make_chunk_id(meta.get("source", ""), text),
            metadata=dict(meta, chunk_strategy="verse"),
        )

    def chunk(self, docs: list[Document]) -> list[Chunk]:
        result = []
        for doc in docs:
            result.extend(self.chunk_text(doc.text, doc.metadata))
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Sliding-window chunker
# ─────────────────────────────────────────────────────────────────────────────

class SlidingWindowChunker:
    """
    Fixed-size character window with overlap.

    Splits on word boundaries (never mid-word) using a right-facing look-back
    to find the nearest space before the character limit.

    Suitable for dense prose that lacks verse numbering.
    """

    def __init__(
        self,
        chunk_size: int = 600,
        overlap: int = 100,
        min_chars: int = 80,
    ) -> None:
        self._size = chunk_size
        self._overlap = overlap
        self._min = min_chars

    def chunk_text(self, text: str, base_metadata: dict) -> list[Chunk]:
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self._size, len(text))
            # Step back to word boundary
            if end < len(text):
                boundary = text.rfind(" ", start, end)
                if boundary > start + self._min:
                    end = boundary

            segment = text[start:end].strip()
            if len(segment) >= self._min:
                chunks.append(Chunk(
                    text=segment,
                    chunk_id=_make_chunk_id(base_metadata.get("source", ""), segment),
                    metadata=dict(base_metadata, chunk_strategy="sliding_window",
                                  chunk_start=start, chunk_end=end),
                ))
            start = end - self._overlap
            if start >= len(text):
                break

        return chunks

    def chunk(self, docs: list[Document]) -> list[Chunk]:
        result = []
        for doc in docs:
            result.extend(self.chunk_text(doc.text, doc.metadata))
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Smart chunker (primary interface)
# ─────────────────────────────────────────────────────────────────────────────

class SmartChunker:
    """
    Tries ``VerseAwareChunker`` first; falls back to ``SlidingWindowChunker``.

    Also deduplicates chunks by chunk_id so re-ingesting a file doesn't
    create duplicate embeddings in the vector store.

    Parameters
    ----------
    chunk_size : Target characters per chunk (sliding window fallback).
    overlap    : Character overlap between adjacent sliding-window chunks.
    """

    def __init__(
        self,
        chunk_size: int = 600,
        overlap: int = 100,
    ) -> None:
        self._verse = VerseAwareChunker()
        self._sliding = SlidingWindowChunker(chunk_size=chunk_size, overlap=overlap)

    def chunk(self, docs: list[Document]) -> list[Chunk]:
        """
        Chunk a list of Documents, returning deduplicated Chunks.

        Parameters
        ----------
        docs : Documents from any Loader.

        Returns
        -------
        list[Chunk]
            Ordered by (source, position), deduplicated by chunk_id.
        """
        all_chunks: list[Chunk] = []
        seen_ids: set[str] = set()

        for doc in docs:
            if self._verse.can_handle(doc.text):
                doc_chunks = self._verse.chunk_text(doc.text, doc.metadata)
            else:
                doc_chunks = self._sliding.chunk_text(doc.text, doc.metadata)

            for chunk in doc_chunks:
                if chunk.chunk_id not in seen_ids:
                    seen_ids.add(chunk.chunk_id)
                    all_chunks.append(chunk)

        return all_chunks

    def chunk_single(self, doc: Document) -> list[Chunk]:
        """Chunk a single Document."""
        return self.chunk([doc])
