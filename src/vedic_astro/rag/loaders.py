"""
loaders.py — Document loaders for classical astrology texts and datasets.

Supported formats
-----------------
- ``.txt``  : Plain UTF-8 text (BPHS, Saravali, Phaladeepika, etc.)
- ``.pdf``  : PDF files (requires ``pypdf``)
- ``.json`` : JSON array of objects with a configurable text field
- directory : Recursively loads all matching files

Each loader returns a list of ``Document`` objects that carry the original
text plus a metadata dict (source path, page number, chapter title, etc.).
Metadata flows through chunking and into the FAISS sidecar so retrieval
results can cite their original source.

Usage
-----
    from vedic_astro.rag.loaders import DirectoryLoader

    docs = DirectoryLoader("data/raw/texts").load()
    print(docs[0].metadata["source"])  # "data/raw/texts/bphs.txt"
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Core data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Document:
    """A single document unit with text and provenance metadata."""
    text: str
    metadata: dict = field(default_factory=dict)

    @property
    def source(self) -> str:
        return self.metadata.get("source", "unknown")

    @property
    def word_count(self) -> int:
        return len(self.text.split())


# ─────────────────────────────────────────────────────────────────────────────
# Text loader
# ─────────────────────────────────────────────────────────────────────────────

class TextLoader:
    """
    Loads a plain-text file as a single Document.

    Tries to detect chapter boundaries (lines matching ``Chapter N`` or
    numeric headings) and splits there, attaching chapter metadata.
    Falls back to a single document if no chapters detected.
    """

    # Chapter detection patterns
    _CHAPTER_RE = re.compile(
        r"^(?:chapter|adhyaya|shloka|ch\.?)\s*\d+",
        re.IGNORECASE,
    )

    def __init__(self, path: str | Path, encoding: str = "utf-8") -> None:
        self._path = Path(path)
        self._encoding = encoding

    def load(self) -> list[Document]:
        """Load and return one Document per detected chapter (or one total)."""
        try:
            raw = self._path.read_text(encoding=self._encoding, errors="replace")
        except OSError as exc:
            logger.error("Cannot read %s: %s", self._path, exc)
            return []

        raw = self._clean(raw)
        chapters = self._split_chapters(raw)

        if not chapters:
            return [Document(text=raw, metadata={"source": str(self._path), "chapter": 0})]

        docs = []
        for i, chapter_text in enumerate(chapters):
            if len(chapter_text.strip()) < 50:
                continue
            docs.append(Document(
                text=chapter_text.strip(),
                metadata={
                    "source": str(self._path),
                    "source_name": self._path.stem.upper(),
                    "chapter": i + 1,
                    "page": None,
                },
            ))
        return docs

    @staticmethod
    def _clean(text: str) -> str:
        """Normalise whitespace and remove BOM."""
        text = text.lstrip("\ufeff")              # BOM
        text = re.sub(r"\r\n", "\n", text)        # CRLF → LF
        text = re.sub(r" {3,}", "  ", text)       # collapse excessive spaces
        return text

    def _split_chapters(self, text: str) -> list[str]:
        """Split on chapter headings. Returns [] if none found."""
        lines = text.split("\n")
        chapter_indices = [i for i, ln in enumerate(lines) if self._CHAPTER_RE.match(ln.strip())]
        if len(chapter_indices) < 2:
            return []

        chunks = []
        for start, end in zip(chapter_indices, chapter_indices[1:] + [len(lines)]):
            chunks.append("\n".join(lines[start:end]))
        return chunks


# ─────────────────────────────────────────────────────────────────────────────
# PDF loader
# ─────────────────────────────────────────────────────────────────────────────

class PDFLoader:
    """
    Loads a PDF file, one Document per page.

    Requires: ``pip install pypdf``
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> list[Document]:
        try:
            from pypdf import PdfReader  # type: ignore[import]
        except ImportError:
            logger.error("pypdf not installed. Run: pip install pypdf")
            return []

        try:
            reader = PdfReader(str(self._path))
        except Exception as exc:
            logger.error("Cannot read PDF %s: %s", self._path, exc)
            return []

        docs = []
        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if len(text.strip()) < 20:
                continue
            docs.append(Document(
                text=text.strip(),
                metadata={
                    "source": str(self._path),
                    "source_name": self._path.stem.upper(),
                    "page": page_num,
                    "chapter": None,
                },
            ))

        logger.debug("PDFLoader: %d pages from %s", len(docs), self._path.name)
        return docs


# ─────────────────────────────────────────────────────────────────────────────
# JSON loader
# ─────────────────────────────────────────────────────────────────────────────

class JSONLoader:
    """
    Loads a JSON file (array of objects) as Documents.

    Each object becomes one Document; text is extracted from *text_field*.
    Additional object keys are preserved as metadata.
    """

    def __init__(
        self,
        path: str | Path,
        text_field: str = "text",
        metadata_fields: Optional[list[str]] = None,
    ) -> None:
        self._path = Path(path)
        self._text_field = text_field
        self._metadata_fields = metadata_fields or []

    def load(self) -> list[Document]:
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Cannot read JSON %s: %s", self._path, exc)
            return []

        if not isinstance(data, list):
            data = [data]

        docs = []
        for i, obj in enumerate(data):
            if not isinstance(obj, dict):
                continue
            text = str(obj.get(self._text_field, "")).strip()
            if not text:
                continue

            meta = {
                "source": str(self._path),
                "source_name": self._path.stem,
                "record_index": i,
            }
            for key in self._metadata_fields:
                if key in obj:
                    meta[key] = obj[key]

            docs.append(Document(text=text, metadata=meta))

        logger.debug("JSONLoader: %d records from %s", len(docs), self._path.name)
        return docs


# ─────────────────────────────────────────────────────────────────────────────
# Directory loader
# ─────────────────────────────────────────────────────────────────────────────

_LOADER_MAP: dict[str, type] = {
    ".txt": TextLoader,
    ".pdf": PDFLoader,
}


class DirectoryLoader:
    """
    Recursively loads all supported documents from a directory.

    Supported extensions: ``.txt``, ``.pdf``
    Files matching ``exclude_patterns`` are skipped.
    """

    def __init__(
        self,
        directory: str | Path,
        glob: str = "**/*",
        exclude_patterns: Optional[list[str]] = None,
    ) -> None:
        self._dir = Path(directory)
        self._glob = glob
        self._exclude = exclude_patterns or []

    def load(self) -> list[Document]:
        if not self._dir.exists():
            logger.warning("Directory not found: %s", self._dir)
            return []

        docs: list[Document] = []
        for path in sorted(self._dir.glob(self._glob)):
            if not path.is_file():
                continue
            if any(pat in str(path) for pat in self._exclude):
                continue

            loader_cls = _LOADER_MAP.get(path.suffix.lower())
            if loader_cls is None:
                continue

            try:
                loaded = loader_cls(path).load()
                docs.extend(loaded)
                logger.info("Loaded %d docs from %s", len(loaded), path.name)
            except Exception as exc:
                logger.warning("Error loading %s: %s", path, exc)

        logger.info("DirectoryLoader: %d total documents from %s", len(docs), self._dir)
        return docs

    def iter_docs(self) -> Iterator[Document]:
        """Lazy iterator — avoids loading all files into memory at once."""
        for doc in self.load():
            yield doc
