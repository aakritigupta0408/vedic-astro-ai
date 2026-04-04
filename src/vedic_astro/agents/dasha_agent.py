"""
dasha_agent.py — Specialist agent for Vimshottari Dasha interpretation.

Scope: Active Maha-Antardasha window, the two lords' natal placement/dignity,
their mutual relationship (friend/enemy/neutral), and timing predictions.
Does NOT interpret transits.
"""

from __future__ import annotations

from vedic_astro.agents.base import AgentInput, AgentOutput, BaseAgent
from vedic_astro.settings import settings


class DashaAgent(BaseAgent):
    """Interprets the active Vimshottari Dasha period."""

    name = "dasha"
    system_prompt = (
        "You are a Vedic astrology specialist in Vimshottari Dasha timing. "
        "Focus on the Maha dasha lord and Antardasha lord: their natal positions, "
        "dignities, mutual relationship (friendship/enmity), and house rulership. "
        "Connect to the user's query domain (career/relationships/health). "
        "One focused paragraph, max 4 sentences. Be specific about timing."
    )

    @property
    def model(self) -> str:
        return settings.dasha_agent_model

    @property
    def max_tokens(self) -> int:
        return settings.dasha_agent_max_tokens

    def build_user_prompt(self, inp: AgentInput) -> str:
        data = inp.engine_data
        rules_block = ""
        if inp.retrieved_rules:
            rules_block = "\n\nClassical dasha rules:\n" + "\n".join(
                f"- {r}" for r in inp.retrieved_rules[:4]
            )

        return (
            f"Query: {inp.query}\n\n"
            f"Active Dasha Window:\n{data}\n"
            f"{rules_block}\n\n"
            "Write a focused dasha interpretation with timing predictions."
        )
