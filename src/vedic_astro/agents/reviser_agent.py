"""
reviser_agent.py — Targeted revision pass triggered by a failing critic score.

The reviser receives:
- The original synthesis narrative
- The critic's list of specific issues
- The classical rules that were violated

It produces a corrected narrative.  One revision pass maximum
(settings.max_revision_passes = 1) to prevent infinite loops.
"""

from __future__ import annotations

import logging

from vedic_astro.agents.critic_agent import CriticResult
from vedic_astro.tools.llm_client import get_llm_client
from vedic_astro.settings import settings

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are a Vedic astrology editor performing a targeted correction pass.
You will receive:
1. A draft reading that failed quality checks.
2. A list of specific issues found by the critic.
3. Classical rules that must be respected.

Your task: rewrite the reading to fix ONLY the listed issues.
- Do not change correct parts.
- Do not add new interpretations beyond what the original data supports.
- Keep the same structure and length.
- Address the user's query directly.
"""


class ReviserAgent:
    """Targeted correction pass for a failed synthesis."""

    def __init__(self) -> None:
        self._llm = get_llm_client()

    async def revise(
        self,
        original: str,
        critic_result: CriticResult,
        query: str,
        classical_rules: list[str],
    ) -> str:
        """
        Revise the synthesis narrative based on critic feedback.

        Parameters
        ----------
        original       : The failed synthesis text.
        critic_result  : CriticResult with issue list and scores.
        query          : Original user query for context.
        classical_rules: Rules the critic flagged as violated.

        Returns
        -------
        str
            Corrected narrative.
        """
        issues_str = "\n".join(f"- {i}" for i in critic_result.issues) or "General quality improvement needed."
        rules_str = (
            "\n".join(f"- {r}" for r in classical_rules[:5])
            if classical_rules else "Apply standard Parashari principles."
        )

        user = (
            f"User query: {query}\n\n"
            f"Issues to fix:\n{issues_str}\n\n"
            f"Classical rules to apply:\n{rules_str}\n\n"
            f"Draft reading:\n{original}\n\n"
            "Rewrite to correct only the listed issues."
        )

        revised = await self._llm.complete(
            system=_SYSTEM,
            user=user,
            model=settings.reviser_model,
            max_tokens=settings.synthesis_agent_max_tokens,
            temperature=0.3,
            use_cache=False,   # always generate fresh revision
        )

        logger.info("Reviser: completed revision (critic score was %.2f)", critic_result.composite_score)
        return revised.strip()
