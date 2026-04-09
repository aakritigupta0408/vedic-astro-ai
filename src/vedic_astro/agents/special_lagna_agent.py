"""
special_lagna_agent.py — Specialist agent for special lagnas and Arudha Padas.
"""

from __future__ import annotations

from vedic_astro.agents.base import AgentInput, BaseAgent
from vedic_astro.settings import settings


class SpecialLagnaAgent(BaseAgent):
    """
    Interprets special lagnas (Hora, Ghati, Bhava, Pranapada, Indu, Sri,
    Varnada, Karakamsha) and Arudha Padas (AL, A7, A10, UL) for the query.
    """

    name = "special_lagna"
    system_prompt = (
        "You are a Vedic astrology specialist in special lagnas and Arudha Padas. "
        "Arudha Padas reveal the external reality — what the world sees — as opposed "
        "to the natal chart which shows inner potential. "
        "Focus on: "
        "AL (Arudha Lagna) = social image; "
        "A7/UL (Upapada) = partner reality; "
        "A10 = career reputation; "
        "A2 = visible wealth; "
        "Karakamsha = soul's true purpose. "
        "For special lagnas, Hora Lagna shows wealth potential, Ghati Lagna shows authority. "
        "Compare each pada/lagna's sign and lord to the natal D1 promise. "
        "One focused paragraph, max 5 sentences. Name specific signs and lords."
    )

    @property
    def model(self) -> str:
        return settings.divisional_agent_model

    @property
    def max_tokens(self) -> int:
        return settings.divisional_agent_max_tokens

    def build_user_prompt(self, inp: AgentInput) -> str:
        data = inp.engine_data
        rules_block = ""
        if inp.retrieved_rules:
            rules_block = "\n\nClassical rules:\n" + "\n".join(
                f"- {r}" for r in inp.retrieved_rules[:4]
            )

        # Highlight query-relevant padas
        query_lower = inp.query.lower()
        focus_padas = []
        if any(w in query_lower for w in ("career", "job", "profession", "business")):
            focus_padas = ["A10", "AL", "Karakamsha"]
        elif any(w in query_lower for w in ("marriage", "spouse", "partner", "relationship")):
            focus_padas = ["UL", "A7", "AL", "Karakamsha"]
        elif any(w in query_lower for w in ("wealth", "money", "finance")):
            focus_padas = ["A2", "AL", "Hora Lagna"]
        elif any(w in query_lower for w in ("spiritual", "spirituality", "soul")):
            focus_padas = ["Karakamsha", "Swamsha", "AL"]
        else:
            focus_padas = ["AL", "A10", "Karakamsha"]

        focus_line = f"Query-relevant padas/lagnas to emphasise: {', '.join(focus_padas)}"

        return (
            f"Query: {inp.query}\n"
            f"{focus_line}\n\n"
            f"Special Lagna & Arudha Pada Data:\n{data}\n"
            f"{rules_block}\n\n"
            "Interpret how these special lagnas and arudha padas answer the query."
        )
