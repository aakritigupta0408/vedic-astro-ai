from __future__ import annotations

import logging
from dataclasses import dataclass

from vedic_astro.tools.llm_client import get_llm_client
from vedic_astro.settings import settings

logger = logging.getLogger(__name__)

_SYSTEM_BASE = """\
You are a senior Vedic astrology synthesist. You receive focused sub-reports
from specialist agents and a QUANTITATIVE SCORE BREAKDOWN. Your job is to
produce ONE integrated reading whose narrative directly matches the numbers.

Weighting principle (reflected in the score breakdown you receive):
- Natal chart D1+D9 Navamsha: foundational promise — ~35% weight
- Vimshottari Dasha: active timing — ~30% weight
- Gochara (transit): current activation — ~25% weight
- Yoga/Dosha net effect: ~10% weight

CRITICAL RULES:
1. State the composite score and interpretation in your FIRST sentence.
   Example: "Your career chart scores 0.68/1.00 (Strong Positive)…"
2. Name the 1-2 factors that most drove the score (highest weighted contribution).
3. Name any significant drag factors (low score on a high-weight layer).
4. Only include a substantive point if confirmed by ≥2 layers.
5. Do not contradict the classical rules cited by specialist agents.
6. Use plain English — no Sanskrit jargon without explanation.
7. End with concrete 3-month actionable guidance.
8. Max {max_tokens} tokens.
"""

# Domain-specific focus hints injected into the system prompt so the synthesis
# emphasises the correct houses, planets, and Vargas for the query topic.
_DOMAIN_FOCUS: dict[str, str] = {
    "career":       "Primary indicators: 10th house (10L), Sun, Saturn, D10 (Dashamsha). Secondary: 6th, 11th houses.",
    "profession":   "Primary indicators: 10th house (10L), Sun, Saturn, D10 (Dashamsha). Secondary: 6th, 11th houses.",
    "job":          "Primary indicators: 10th house (10L), Sun, Saturn, D10 (Dashamsha). Secondary: 6th, 11th houses.",
    "business":     "Primary indicators: 7th house (partnerships), 10th house, Mercury, Jupiter. D10 Dashamsha.",
    "marriage":     "Primary indicators: 7th house (7L), Venus, Moon, D9 (Navamsha). Secondary: 2nd house (family).",
    "partner":      "Primary indicators: 7th house (7L), Venus, Moon, D9 (Navamsha). Secondary: 2nd house (family).",
    "spouse":       "Primary indicators: 7th house (7L), Venus, Moon, D9 (Navamsha). Secondary: 2nd house (family).",
    "relationship": "Primary indicators: 7th house (7L), Venus, Moon, D9 (Navamsha). Secondary: 2nd house (family).",
    "children":     "Primary indicators: 5th house (5L), Jupiter, Moon, D7 (Saptamsha). Secondary: 9th house.",
    "child":        "Primary indicators: 5th house (5L), Jupiter, Moon, D7 (Saptamsha). Secondary: 9th house.",
    "wealth":       "Primary indicators: 2nd house (2L), 11th house (11L), Jupiter, Venus, D2 (Hora). Dhana yogas.",
    "money":        "Primary indicators: 2nd house (2L), 11th house (11L), Jupiter, Venus, D2 (Hora). Dhana yogas.",
    "finance":      "Primary indicators: 2nd house (2L), 11th house (11L), Jupiter, Venus, D2 (Hora). Dhana yogas.",
    "health":       "Primary indicators: 1st house (1L), 6th house, Sun, Mars, D3 (Drekkana). Nakshatras.",
    "disease":      "Primary indicators: 6th house (6L), 8th house, Saturn, Rahu, D3 (Drekkana).",
    "longevity":    "Primary indicators: 8th house (8L), 1st house, Saturn, D3 (Drekkana). Maraka planets (2L, 7L).",
    "spirituality": "Primary indicators: 9th house (9L), 12th house, Jupiter, Ketu, D9 + D20 (Vimshamsha).",
    "spiritual":    "Primary indicators: 9th house (9L), 12th house, Jupiter, Ketu, D9 + D20 (Vimshamsha).",
    "property":     "Primary indicators: 4th house (4L), Mars, Moon, D4 (Chaturthamsha).",
    "home":         "Primary indicators: 4th house (4L), Mars, Moon, D4 (Chaturthamsha).",
    "education":    "Primary indicators: 4th house (4L), 5th house (5L), Mercury, Jupiter, D24 (Siddhamsha).",
    "travel":       "Primary indicators: 3rd house (short), 9th house (long), Moon, Rahu, 12th house.",
}


def _get_domain_focus(query: str) -> str:
    """Pick the most relevant domain hint for the query, or empty string."""
    q = query.lower()
    for keyword, hint in _DOMAIN_FOCUS.items():
        if keyword in q:
            return hint
    return ""


@dataclass
class SynthesisInput:
    query: str
    natal_narrative: str
    dasha_narrative: str
    transit_narrative: str
    divisional_narrative: str
    retrieved_cases: list[str]
    score_summary: str = ""
    score_table: str = ""


@dataclass
class SynthesisOutput:
    narrative: str
    tokens_used: int = 0


class SynthesisAgent:
    """Combines all specialist narratives into one integrated reading."""

    def __init__(self) -> None:
        self._llm = get_llm_client()

    async def run(self, inp: SynthesisInput) -> SynthesisOutput:
        domain_hint = _get_domain_focus(inp.query)
        domain_line = f"\nDomain focus for this query: {domain_hint}" if domain_hint else ""
        system = (_SYSTEM_BASE + domain_line).format(max_tokens=settings.synthesis_agent_max_tokens)

        cases_block = ""
        if inp.retrieved_cases:
            cases_block = "\n\nSimilar reference cases:\n" + "\n".join(
                f"- {c}" for c in inp.retrieved_cases[:3]
            )

        if inp.score_table:
            score_block = f"\n\n=== QUANTITATIVE SCORE ===\n{inp.score_table}\n"
        elif inp.score_summary:
            score_block = f"\n\n=== QUANTITATIVE SCORE ===\n{inp.score_summary}\n"
        else:
            score_block = ""

        user = (
            f"User query: {inp.query}\n"
            f"{score_block}\n"
            f"=== NATAL AGENT (D1+D9) ===\n{inp.natal_narrative}\n\n"
            f"=== DASHA AGENT ===\n{inp.dasha_narrative}\n\n"
            f"=== TRANSIT AGENT ===\n{inp.transit_narrative}\n\n"
            f"=== DIVISIONAL AGENT ===\n{inp.divisional_narrative}\n"
            f"{cases_block}\n\n"
            "Synthesise into one integrated, query-specific Vedic reading. "
            "Your first sentence MUST state the composite score from the table above."
        )

        narrative = await self._llm.complete(
            system=system,
            user=user,
            model=settings.synthesis_model,
            max_tokens=settings.synthesis_agent_max_tokens,
            temperature=0.4,
        )

        return SynthesisOutput(narrative=narrative.strip())
