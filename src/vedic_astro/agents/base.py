from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from vedic_astro.tools.llm_client import get_llm_client
from vedic_astro.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class AgentInput:
    chart_id: str
    query: str
    engine_data: dict[str, Any]
    retrieved_rules: list[str]
    retrieved_cases: list[str]


@dataclass
class AgentOutput:
    agent_name: str
    narrative: str
    key_factors: list[str]
    tokens_used: int = 0
    from_cache: bool = False


class BaseAgent(ABC):
    """Abstract base for all Vedic astrology specialist agents.

    Each subclass has one responsibility: take deterministic engine output,
    optionally use retrieved classical rules, and produce a focused narrative
    via the LLM. Agents must not call each other or perform astronomical math.
    """

    name: str = "base"
    system_prompt: str = ""

    def __init__(self) -> None:
        self._llm = get_llm_client()

    @abstractmethod
    def build_user_prompt(self, inp: AgentInput) -> str: ...

    @property
    def model(self) -> str:
        return settings.synthesis_model

    @property
    def max_tokens(self) -> int:
        return 600

    async def run(self, inp: AgentInput) -> AgentOutput:
        user_prompt = self.build_user_prompt(inp)
        logger.debug("%s agent calling LLM (model=%s)", self.name, self.model)

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
        sentences = re.split(r"(?<=[.!?])\s+", narrative.strip())
        return [s.strip() for s in sentences if len(s.strip()) > 20][:5]
