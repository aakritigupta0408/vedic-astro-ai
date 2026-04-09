from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from vedic_astro.tools.llm_client import get_llm_client
from vedic_astro.settings import settings

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are a strict quality controller for Vedic astrology readings.
Evaluate the reading on 4 criteria (0.0–1.0 each):

1. classical_accuracy : Does it follow classical Parashari rules?
2. query_relevance    : Does it directly answer the user's query?
3. specificity        : Are planets, signs, and houses named concretely?
4. consistency        : No internal contradictions between layers?

Return ONLY valid JSON:
{"classical_accuracy": 0.0, "query_relevance": 0.0, "specificity": 0.0, "consistency": 0.0, "issues": ["...", "..."]}

If a criterion cannot be evaluated (no rules provided), score it 0.8.
"""


@dataclass
class CriticResult:
    classical_accuracy: float
    query_relevance: float
    specificity: float
    consistency: float
    composite_score: float
    issues: list[str]
    passed: bool


class CriticAgent:
    """Binary PASS/FAIL quality gate for the synthesis output."""

    def __init__(self) -> None:
        self._llm = get_llm_client()

    async def evaluate(
        self,
        query: str,
        synthesis: str,
        classical_rules: list[str],
    ) -> CriticResult:
        rules_str = (
            "\n".join(f"- {r}" for r in classical_rules[:6])
            if classical_rules else "No rules provided."
        )
        user = (
            f"User query: {query}\n\n"
            f"Classical rules to check against:\n{rules_str}\n\n"
            f"Reading to evaluate:\n{synthesis}\n\n"
            "Evaluate and return JSON."
        )

        raw = await self._llm.complete(
            system=_SYSTEM,
            user=user,
            model=settings.critic_model,
            max_tokens=settings.critic_agent_max_tokens,
            temperature=0.0,
            use_cache=False,
        )

        return self._parse_result(raw)

    def _parse_result(self, raw: str) -> CriticResult:
        try:
            clean = re.sub(r"```json?\s*|\s*```", "", raw).strip()
            data = json.loads(clean)

            ca  = float(data.get("classical_accuracy", 0.8))
            qr  = float(data.get("query_relevance", 0.8))
            sp  = float(data.get("specificity", 0.8))
            co  = float(data.get("consistency", 0.8))
            issues = data.get("issues", [])

            composite = round(0.35 * ca + 0.35 * qr + 0.20 * sp + 0.10 * co, 3)
            passed = composite >= settings.critic_pass_threshold

            return CriticResult(
                classical_accuracy=ca,
                query_relevance=qr,
                specificity=sp,
                consistency=co,
                composite_score=composite,
                issues=issues,
                passed=passed,
            )
        except Exception as exc:
            # Parsing failure → pass with a note rather than blocking the reading
            logger.warning("Critic parse failed (%s); defaulting to PASS", exc)
            return CriticResult(
                classical_accuracy=0.8,
                query_relevance=0.8,
                specificity=0.8,
                consistency=0.8,
                composite_score=0.8,
                issues=["Critic output could not be parsed"],
                passed=True,
            )
