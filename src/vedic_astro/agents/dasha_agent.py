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
        "Your analysis MUST address these interdependences explicitly:\n"
        "1. The dasha lord's NATAL strength (D1 dignity + house) sets the promise.\n"
        "2. The dasha lord's D9 (Navamsha) dignity determines how FULLY that promise manifests "
        "— exalted in D9 amplifies, debilitated curtails.\n"
        "3. For career queries, also check the dasha lord's D10 (Dashamsha) position.\n"
        "4. Whether the dasha lord IS one of the yoga-forming planets — if yes, the yoga is "
        "now FRUCTIFYING (actively delivering results), not just natally present.\n"
        "5. Maha/Antar lord mutual relationship and their combined house rulership.\n"
        "One focused paragraph, max 5 sentences. Be specific: name the lord, its D9 state, "
        "and whether it activates any yogas."
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
