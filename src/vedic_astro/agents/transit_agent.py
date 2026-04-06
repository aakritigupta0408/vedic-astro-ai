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
        "Your analysis MUST address these interdependences explicitly:\n"
        "1. Use the dual-anchor method: 60% weight to Moon sign, 40% to Lagna.\n"
        "2. DASHA-TRANSIT CONFLUENCE: if a transiting planet is conjunct the natal "
        "dasha lord (within 5°), this is a DOUBLE ACTIVATION — name it explicitly.\n"
        "3. TRANSIT-YOGA ACTIVATION: if a transiting planet is conjunct (within 3°) "
        "a natal yoga-forming planet, that yoga is now triggered — name which yoga.\n"
        "4. Sade Sati if active — it overrides individual gochara for Moon matters.\n"
        "5. Focus on Saturn, Jupiter, Rahu/Ketu transits as primary timing triggers.\n"
        "One focused paragraph, max 5 sentences. Name specific activations."
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
