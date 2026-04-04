"""
transit_agent.py — Specialist agent for live transit (Gochara) interpretation.

Scope: Current planet positions over natal chart, Gochara strength, Sade Sati,
Jupiter/Saturn transit milestones.  Does NOT interpret natal placements alone.
"""

from __future__ import annotations

from vedic_astro.agents.base import AgentInput, BaseAgent
from vedic_astro.settings import settings


class TransitAgent(BaseAgent):
    """Interprets live Gochara (transit) overlay on the natal chart."""

    name = "transit"
    system_prompt = (
        "You are a Vedic astrology specialist in Gochara (transit) analysis. "
        "Use the dual-anchor method: 60% weight to Moon sign, 40% to Lagna. "
        "Highlight Sade Sati if active. Focus on Saturn, Jupiter, Rahu/Ketu transits first. "
        "Connect transits to the query domain. One paragraph, max 4 sentences."
    )

    @property
    def model(self) -> str:
        return settings.transit_agent_model

    @property
    def max_tokens(self) -> int:
        return settings.transit_agent_max_tokens

    def build_user_prompt(self, inp) -> str:
        data = inp.engine_data
        rules_block = ""
        if inp.retrieved_rules:
            rules_block = "\n\nClassical gochara rules:\n" + "\n".join(
                f"- {r}" for r in inp.retrieved_rules[:4]
            )

        return (
            f"Query: {inp.query}\n\n"
            f"Transit Overlay Data:\n{data}\n"
            f"{rules_block}\n\n"
            "Write a focused gochara interpretation."
        )
