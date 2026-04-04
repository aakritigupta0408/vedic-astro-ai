"""
rule_extractor.py — Convert text chunks into structured ExtractedRule objects.

Two extraction strategies
--------------------------
1. **LLM extraction** (high quality, slow, expensive):
   Sends each chunk to Claude Haiku with a strict JSON schema prompt.
   Results are cached per chunk_id (permanent) so re-running the pipeline
   never re-processes already-extracted chunks.

2. **Regex extraction** (fast, lower recall):
   Pattern-matches common Vedic rule sentence structures.
   Used as fallback when LLM is unavailable or rate-limited.

The ``RuleExtractor`` class runs strategy 1 with strategy 2 as fallback,
processing chunks in async batches with a configurable concurrency limit.

Output
------
Extracted rules are saved to ``data/processed/rules.json``.  The FAISS index
is then built from this file by ``scripts/build_index.py``.

Usage (offline pipeline)
------------------------
    extractor = RuleExtractor()
    rules = await extractor.extract_batch(chunks, concurrency=8)
    with open("data/processed/rules.json", "w") as f:
        json.dump([r.model_dump() for r in rules], f, indent=2)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

class ExtractedRule(BaseModel):
    """
    A structured Vedic astrology rule extracted from a classical text.

    Fields
    ------
    rule_id     : Unique identifier (chunk_id[:8] + sequential suffix).
    text        : Verbatim or lightly normalised source text.
    condition   : "When/If [planetary configuration]" clause.
    outcome     : "Then [effect/result]" clause.
    domain      : Broad astrological domain.
    charts      : Relevant divisional charts (e.g. ["D1", "D9"]).
    polarity    : Whether the rule describes a positive, negative, or neutral outcome.
    planets     : Navagrahas mentioned (lowercase).
    houses      : House numbers referenced (1–12).
    signs       : Zodiac signs mentioned (lowercase).
    source      : Classical text and chapter/verse reference.
    confidence  : Extraction confidence (1.0 = LLM confirmed, 0.5 = regex).
    """

    rule_id:    str
    text:       str
    condition:  str
    outcome:    str
    domain:     Literal["natal", "dasha", "transit", "divisional", "yoga", "dosha", "panchang", "general"]
    charts:     list[str] = Field(default_factory=lambda: ["D1"])
    polarity:   Literal["positive", "negative", "neutral"] = "neutral"
    planets:    list[str] = Field(default_factory=list)
    houses:     list[int] = Field(default_factory=list)
    signs:      list[str] = Field(default_factory=list)
    source:     str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Regex-based fallback extractor
# ─────────────────────────────────────────────────────────────────────────────

_PLANETS   = ["sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu"]
_SIGNS     = ["aries", "taurus", "gemini", "cancer", "leo", "virgo",
              "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces"]
_MALEFIC_KW = ["afflicted", "malefic", "enemy", "debilitated", "weak", "dosha",
               "danger", "suffering", "disease", "loss", "delay", "obstacle"]
_BENEFIC_KW = ["exalted", "strong", "yoga", "prosperous", "fortune", "wisdom",
               "wealth", "happiness", "success", "gains", "powerful"]
_HOUSE_RE  = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+house\b", re.IGNORECASE)
_DOMAIN_KW = {
    "dasha":      ["dasha", "antardasha", "period", "maha dasha"],
    "transit":    ["transit", "gochara", "transiting"],
    "divisional": ["navamsha", "d9", "d10", "dashamsha", "varga"],
    "yoga":       ["yoga", "combination", "conjunction"],
    "dosha":      ["dosha", "affliction", "kuja", "sarpa", "kemdrum"],
    "panchang":   ["tithi", "nakshatra", "vara", "karana", "yoga"],  # NithyaYoga
}


def _classify_domain(text: str) -> str:
    tl = text.lower()
    for domain, kws in _DOMAIN_KW.items():
        if any(kw in tl for kw in kws):
            return domain
    return "natal"


def _classify_polarity(text: str) -> str:
    tl = text.lower()
    malefic_hits = sum(1 for kw in _MALEFIC_KW if kw in tl)
    benefic_hits = sum(1 for kw in _BENEFIC_KW if kw in tl)
    if benefic_hits > malefic_hits:
        return "positive"
    if malefic_hits > benefic_hits:
        return "negative"
    return "neutral"


def _extract_planets(text: str) -> list[str]:
    tl = text.lower()
    return [p for p in _PLANETS if p in tl]


def _extract_houses(text: str) -> list[int]:
    return [int(m.group(1)) for m in _HOUSE_RE.finditer(text) if 1 <= int(m.group(1)) <= 12]


def _extract_signs(text: str) -> list[str]:
    tl = text.lower()
    return [s for s in _SIGNS if s in tl]


def _extract_charts(text: str) -> list[str]:
    charts = ["D1"]
    if any(k in text.lower() for k in ["navamsha", "d9"]):
        charts.append("D9")
    if any(k in text.lower() for k in ["dashamsha", "d10"]):
        charts.append("D10")
    return list(dict.fromkeys(charts))  # deduplicate, preserve order


# Sentence-level split patterns for condition/outcome detection
_CONDITION_STARTS = re.compile(
    r"\b(when|if|whenever|in case|should|wherever|as long as)\b",
    re.IGNORECASE,
)
_OUTCOME_STARTS = re.compile(
    r"\b(then|gives|produces|causes|results in|bestows|confers|indicates|makes)\b",
    re.IGNORECASE,
)


def _split_condition_outcome(text: str) -> tuple[str, str]:
    """Split a rule sentence into condition and outcome halves."""
    # Try splitting on "then" / "gives" / semicolons / em-dash
    for sep in [" then ", " gives ", " produces ", " — ", " – ", "; "]:
        idx = text.lower().find(sep)
        if idx > 10:
            return text[:idx].strip(), text[idx + len(sep):].strip()

    # Try splitting at first period inside the sentence
    parts = text.split(". ", 1)
    if len(parts) == 2 and len(parts[0]) > 20:
        return parts[0].strip(), parts[1].strip()

    # Fallback: whole text is both condition and outcome
    return text, text


def regex_extract_rules(text: str, source: str = "", chunk_id: str = "") -> list[ExtractedRule]:
    """
    Extract rules from *text* using pattern matching.

    Returns up to ~10 candidate rules per chunk.  Confidence = 0.5.
    """
    # Split into sentences
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    rules = []

    for i, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if len(sentence) < 40:
            continue
        # Must mention at least one planet or house to be a rule
        if not _extract_planets(sentence) and not _extract_houses(sentence):
            continue

        condition, outcome = _split_condition_outcome(sentence)
        rule_id = f"{chunk_id[:8] if chunk_id else 'regex'}_{i:03d}"

        rules.append(ExtractedRule(
            rule_id=rule_id,
            text=sentence,
            condition=condition,
            outcome=outcome,
            domain=_classify_domain(sentence),
            charts=_extract_charts(sentence),
            polarity=_classify_polarity(sentence),
            planets=_extract_planets(sentence),
            houses=_extract_houses(sentence),
            signs=_extract_signs(sentence),
            source=source,
            confidence=0.5,
        ))

    return rules


# ─────────────────────────────────────────────────────────────────────────────
# LLM-based extractor
# ─────────────────────────────────────────────────────────────────────────────

_EXTRACTION_SYSTEM = """\
You are a Vedic astrology scholar. Extract all Vedic astrology rules from the provided text.
For each distinct rule or aphorism, output a JSON object with these exact fields:

{
  "condition": "<When/If [planet/sign/house configuration]>",
  "outcome": "<Then [effect/result in human life]>",
  "domain": "<one of: natal|dasha|transit|divisional|yoga|dosha|panchang|general>",
  "charts": ["D1"],
  "polarity": "<positive|negative|neutral>",
  "planets": ["<planet names in lowercase>"],
  "houses": [<house numbers 1-12>],
  "signs": ["<sign names in lowercase>"],
  "confidence": 0.9
}

Return a JSON array of such objects. If the text contains no astrological rules, return [].
Do NOT include markdown — just the raw JSON array.
"""


class RuleExtractor:
    """
    Extracts structured rules from text chunks.

    Strategy: LLM extraction (cached per chunk) with regex fallback.
    """

    def __init__(self, use_llm: bool = True) -> None:
        self._use_llm = use_llm

    async def extract_chunk(
        self,
        chunk_id: str,
        text: str,
        source: str = "",
    ) -> list[ExtractedRule]:
        """
        Extract rules from a single chunk.

        Results are cached permanently by chunk_id so re-runs skip already-processed chunks.
        """
        cache_key = f"va:rules:chunk:{chunk_id}"

        from vedic_astro.tools.cache import get_cache
        cache = get_cache()
        cached = await cache.get(cache_key)
        if cached is not None:
            try:
                return [ExtractedRule(**r) for r in cached]
            except Exception:
                pass  # fall through to re-extract

        rules: list[ExtractedRule] = []

        if self._use_llm:
            rules = await self._llm_extract(chunk_id, text, source)

        if not rules:
            rules = regex_extract_rules(text, source=source, chunk_id=chunk_id)

        await cache.set(cache_key, [r.model_dump() for r in rules], ttl=0)
        return rules

    async def extract_batch(
        self,
        chunks,  # list[Chunk]
        concurrency: int = 6,
    ) -> list[ExtractedRule]:
        """
        Extract rules from a list of Chunks with bounded concurrency.

        Parameters
        ----------
        chunks      : list of ``Chunk`` objects from ``SmartChunker``.
        concurrency : Max simultaneous LLM requests.

        Returns
        -------
        list[ExtractedRule]
            All rules from all chunks, deduplicated by rule_id.
        """
        sem = asyncio.Semaphore(concurrency)

        async def process(chunk) -> list[ExtractedRule]:
            async with sem:
                return await self.extract_chunk(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    source=chunk.source_name or chunk.source,
                )

        results = await asyncio.gather(*[process(c) for c in chunks])

        seen_ids: set[str] = set()
        all_rules: list[ExtractedRule] = []
        for batch in results:
            for rule in batch:
                if rule.rule_id not in seen_ids:
                    seen_ids.add(rule.rule_id)
                    all_rules.append(rule)

        logger.info("RuleExtractor: %d rules from %d chunks", len(all_rules), len(chunks))
        return all_rules

    async def _llm_extract(
        self,
        chunk_id: str,
        text: str,
        source: str,
    ) -> list[ExtractedRule]:
        """Call Claude Haiku to extract rules as JSON."""
        try:
            from vedic_astro.tools.llm_client import get_llm_client
            from vedic_astro.settings import settings

            client = get_llm_client()
            raw = await client.complete(
                system=_EXTRACTION_SYSTEM,
                user=f"Source: {source}\n\nText:\n{text[:2000]}",
                model=settings.critic_model,   # use small model for extraction
                max_tokens=2048,
                temperature=0.0,
                use_cache=False,   # chunk cache handles this
            )
        except Exception as exc:
            logger.warning("LLM extraction failed for chunk %s: %s", chunk_id, exc)
            return []

        return self._parse_llm_response(raw, source, chunk_id)

    @staticmethod
    def _parse_llm_response(
        raw: str,
        source: str,
        chunk_id: str,
    ) -> list[ExtractedRule]:
        """Parse LLM JSON response into ExtractedRule objects."""
        # Strip markdown code fences
        clean = re.sub(r"```json?\s*|\s*```", "", raw).strip()
        if not clean:
            return []

        try:
            data = json.loads(clean)
        except json.JSONDecodeError:
            # Try extracting the first JSON array
            match = re.search(r"\[.*\]", clean, re.DOTALL)
            if not match:
                return []
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return []

        if not isinstance(data, list):
            return []

        rules = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            try:
                rule = ExtractedRule(
                    rule_id=f"{chunk_id[:8]}_{i:03d}",
                    text=item.get("text", item.get("condition", "") + " " + item.get("outcome", "")),
                    condition=item.get("condition", ""),
                    outcome=item.get("outcome", ""),
                    domain=item.get("domain", "natal"),
                    charts=item.get("charts", ["D1"]),
                    polarity=item.get("polarity", "neutral"),
                    planets=[str(p).lower() for p in item.get("planets", [])],
                    houses=[int(h) for h in item.get("houses", []) if 1 <= int(h) <= 12],
                    signs=[str(s).lower() for s in item.get("signs", [])],
                    source=source,
                    confidence=float(item.get("confidence", 0.9)),
                )
                if rule.condition and rule.outcome:
                    rules.append(rule)
            except Exception as exc:
                logger.debug("Rule parse error item %d: %s", i, exc)

        return rules
