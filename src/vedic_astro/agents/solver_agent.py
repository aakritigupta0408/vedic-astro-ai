from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from vedic_astro.agents.base import AgentInput, AgentOutput, BaseAgent
from vedic_astro.agents.output_formatter import StructuredReading
from vedic_astro.settings import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Yoga / Dosha specialist agent
# ─────────────────────────────────────────────────────────────────────────────

class YogaAgent(BaseAgent):
    """Interprets active yogas and doshas from the natal chart."""

    name = "yoga"
    system_prompt = (
        "You are a Vedic astrology specialist in Yogas (auspicious planetary combinations) "
        "and Doshas (afflictions). Given the list of active yogas and doshas, interpret: "
        "1) Which yogas are most significant for the user's query domain. "
        "2) Whether any doshas require mitigation. "
        "3) Net effect: do yogas outweigh doshas or vice versa? "
        "One focused paragraph, max 4 sentences. Name specific yogas and their effects."
    )

    @property
    def model(self) -> str:
        return settings.natal_agent_model

    @property
    def max_tokens(self) -> int:
        return 400

    def build_user_prompt(self, inp: AgentInput) -> str:
        rules_block = ""
        if inp.retrieved_rules:
            rules_block = "\n\nClassical yoga/dosha rules:\n" + "\n".join(
                f"- {r}" for r in inp.retrieved_rules[:4]
            )
        return (
            f"Query: {inp.query}\n\n"
            f"Yoga & Dosha Data:\n{inp.engine_data}\n"
            f"{rules_block}\n\n"
            "Write a focused yoga/dosha interpretation."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Solver result + single-call entry point
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SolverResult:
    reading: StructuredReading
    pipeline_stages: list[str]
    from_cache: bool = False


class SolverAgent:
    """Single-call entry point that wraps PipelineRunner for the UI and API."""

    def __init__(self) -> None:
        from vedic_astro.agents.pipeline import PipelineRunner
        self._runner = PipelineRunner()

    async def compute_chart(
        self,
        birth,
        query_date: Optional[date] = None,
        domain: str = "general",
        depth: int = 2,
    ):
        """Phase 1 — run all deterministic engine stages, no LLM calls."""
        from vedic_astro.agents.pipeline import ReadingRequest
        request = ReadingRequest(
            birth=birth,
            query="",
            domain=domain,
            query_date=query_date,
            depth=depth,
        )
        return await self._runner.compute_chart(request)

    async def predict(
        self,
        chart_state,
        query: str,
        domain: str = "general",
        calibration_weights: Optional[dict] = None,
    ) -> SolverResult:
        """Phase 3 — run LLM prediction on a pre-computed chart state."""
        reading = await self._runner.predict(
            chart_state, query, domain, calibration_weights
        )
        return SolverResult(
            reading=reading,
            pipeline_stages=chart_state.stages_completed,
        )

    async def solve(
        self,
        birth,
        query: str,
        domain: str = "general",
        query_date: Optional[date] = None,
        depth: int = 2,
    ) -> SolverResult:
        """Run the full pipeline in one call (compute chart + predict)."""
        from vedic_astro.agents.pipeline import ReadingRequest

        request = ReadingRequest(
            birth=birth,
            query=query,
            domain=domain,
            query_date=query_date,
            depth=depth,
        )
        reading = await self._runner.run(request)
        return SolverResult(
            reading=reading,
            pipeline_stages=[],  # state not available after run(); use compute_chart+predict to retain it
        )
