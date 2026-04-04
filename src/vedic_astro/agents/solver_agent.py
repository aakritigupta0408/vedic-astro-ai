"""
solver_agent.py — Yoga/Dosha specialist agent + WeightedReasoning wrapper.

This module provides two additions to the agent layer:

1. ``YogaAgent`` — specialist agent for yoga and dosha interpretation.
   Scope: active yogas (Pancha Mahapurusha, Raj, Dhana, Gajakesari…),
          active doshas (Mangal, Kala Sarpa, Guru Chandala…), net strength.

2. ``SolverResult`` — wrapper carrying structured weighted reasoning
   alongside the final synthesis narrative.

The ``SolverAgent`` class (for external callers) is a convenience wrapper
that runs the full pipeline via ``PipelineRunner`` and returns a
``SolverResult``.  Use this instead of ``PipelineRunner`` when you need
the result from a single-call interface.

Usage
-----
    solver = SolverAgent()
    result = await solver.solve(
        birth=BirthData(year=1990, month=6, day=15, hour=14, minute=30, place="Mumbai"),
        query="What does my chart say about career?",
        domain="career",
    )
    print(result.reading.to_markdown())
"""

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
    """
    Interprets active yogas and doshas from the natal chart.

    Scope: confirms which yogas are present and operative given the dasha
    and transit activation.  Quantifies their likely manifestation.
    """

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
        return settings.natal_agent_model  # same tier as natal agent

    @property
    def max_tokens(self) -> int:
        return 400

    def build_user_prompt(self, inp: AgentInput) -> str:
        data = inp.engine_data
        rules_block = ""
        if inp.retrieved_rules:
            rules_block = "\n\nClassical yoga/dosha rules:\n" + "\n".join(
                f"- {r}" for r in inp.retrieved_rules[:4]
            )
        return (
            f"Query: {inp.query}\n\n"
            f"Yoga & Dosha Data:\n{data}\n"
            f"{rules_block}\n\n"
            "Write a focused yoga/dosha interpretation."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Solver result wrapper
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SolverResult:
    """Full result from SolverAgent."""
    reading: StructuredReading
    pipeline_stages: list[str]      # stages completed in this run
    from_cache: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Solver agent (single-call interface wrapping PipelineRunner)
# ─────────────────────────────────────────────────────────────────────────────

class SolverAgent:
    """
    High-level solver that runs the full deterministic + LLM pipeline.

    This is the single entry point for the Gradio UI and FastAPI endpoint.
    It wraps ``PipelineRunner`` and returns a ``SolverResult``.

    The pipeline follows the strict order:
        natal → dasha → transit → D1–D60 → yogas/doshas
        → weighted score → RAG → specialist LLMs → synthesis
        → conditional critic → conditional reviser → structured output
    """

    def __init__(self) -> None:
        from vedic_astro.agents.pipeline import PipelineRunner
        self._runner = PipelineRunner()

    async def solve(
        self,
        birth,           # BirthData
        query: str,
        domain: str = "general",
        query_date: Optional[date] = None,
        depth: int = 2,
    ) -> SolverResult:
        """
        Run the full pipeline for a single birth + query combination.

        Parameters
        ----------
        birth      : Birth data (BirthData from pipeline.py).
        query      : User's natural-language question.
        domain     : Query domain for scoring (career|marriage|wealth|health|general).
        query_date : Date for transits (default today).
        depth      : Dasha depth (2 = Maha + Antar).

        Returns
        -------
        SolverResult
            Contains the StructuredReading and pipeline metadata.
        """
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
            pipeline_stages=reading.score.notes,  # stages log is in score notes
            from_cache=False,
        )
