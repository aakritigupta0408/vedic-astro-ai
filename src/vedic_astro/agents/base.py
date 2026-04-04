"""
base.py — Abstract base class for all specialist agents.

Each agent has a single responsibility: take deterministic engine output,
optionally retrieve classical rules from RAG, and produce a focused
narrative paragraph via the LLM.

Agents must NOT call other agents (fan-out is orchestrator's job).
Agents must NOT perform any astronomical computation.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from vedic_astro.tools.llm_client import get_llm_client
from vedic_astro.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class AgentInput:
    """Structured input bundle passed to each specialist agent."""
    chart_id: str
    query: str                        # user's original question
    engine_data: dict[str, Any]       # pre-computed engine output (serialised)
    retrieved_rules: list[str]        # RAG results (classical aphorisms)
    retrieved_cases: list[str]        # similar VedAstro cases


@dataclass
class AgentOutput:
    """Structured output from a specialist agent."""
    agent_name: str
    narrative: str                    # focused paragraph for synthesis
    key_factors: list[str]            # bullet-point summary for critic
    tokens_used: int = 0
    from_cache: bool = False


class BaseAgent(ABC):
    """Abstract base for all Vedic astrology specialist agents."""

    name: str = "base"
    system_prompt: str = ""

    def __init__(self) -> None:
        self._llm = get_llm_client()

    @abstractmethod
    def build_user_prompt(self, inp: AgentInput) -> str:
        """Construct the user turn from the agent input bundle."""
        ...

    @property
    def model(self) -> str:
        """Model ID — overridden per-agent via settings."""
        return settings.synthesis_model

    @property
    def max_tokens(self) -> int:
        return 600

    async def run(self, inp: AgentInput) -> AgentOutput:
        """
        Execute the agent: build prompt → call LLM → return narrative.

        Parameters
        ----------
        inp : AgentInput
            Pre-assembled input with engine data and RAG results.

        Returns
        -------
        AgentOutput
            Narrative paragraph and key factors for downstream synthesis.
        """
        user_prompt = self.build_user_prompt(inp)
        logger.debug("%s agent: calling LLM (model=%s)", self.name, self.model)

        narrative = await self._llm.complete(
            system=self.system_prompt,
            user=user_prompt,
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.3,
        )

        key_factors = self._extract_key_factors(narrative)
        return AgentOutput(
            agent_name=self.name,
            narrative=narrative.strip(),
            key_factors=key_factors,
        )

    @staticmethod
    def _extract_key_factors(narrative: str) -> list[str]:
        """
        Extract bullet-point sentences from narrative for the critic.

        Splits on sentence boundaries and returns up to 5 items.
        """
        import re
        sentences = re.split(r"(?<=[.!?])\s+", narrative.strip())
        return [s.strip() for s in sentences if len(s.strip()) > 20][:5]
