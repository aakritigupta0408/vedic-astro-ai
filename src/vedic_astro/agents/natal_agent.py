"""
natal_agent.py — Specialist agent for natal chart interpretation.

Scope: Lagna sign, lagna lord, planet dignities, house strengths (Shadbala),
yogas, doshas, and Chara Karakas.  Does NOT discuss dashas or transits.
"""

from __future__ import annotations

from vedic_astro.agents.base import AgentInput, AgentOutput, BaseAgent
from vedic_astro.settings import settings


class NatalAgent(BaseAgent):
    """Interprets the natal (D1) chart — dignity, strength, yogas, doshas."""

    name = "natal"
    system_prompt = (
        "You are a classical Vedic astrology scholar specialising in the natal (Rashi/D1) chart. "
        "Use only Parashari principles. Interpret in terms of whole-sign houses. "
        "Be precise: state the planet, its sign, house, dignity, and effect. "
        "Avoid vague spiritual language. One coherent paragraph, max 4 sentences."
    )

    @property
    def model(self) -> str:
        return settings.natal_agent_model

    @property
    def max_tokens(self) -> int:
        return settings.natal_agent_max_tokens

    def build_user_prompt(self, inp: AgentInput) -> str:
        data = inp.engine_data
        rules_block = ""
        if inp.retrieved_rules:
            rules_block = "\n\nClassical rules (apply if relevant):\n" + "\n".join(
                f"- {r}" for r in inp.retrieved_rules[:5]
            )

        return (
            f"Query: {inp.query}\n\n"
            f"Natal Chart Data:\n{data}\n"
            f"{rules_block}\n\n"
            "Write a focused natal chart interpretation paragraph."
        )
