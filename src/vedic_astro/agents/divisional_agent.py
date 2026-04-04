"""
divisional_agent.py — Specialist agent for divisional chart (Varga) interpretation.

Scope: D9 (Navamsha) and query-relevant divisional charts only.
Selection logic: map the query topic to the relevant Varga(s).

Topic → Varga mapping
---------------------
career/profession → D10 (Dashamsha)
marriage/partner  → D9 (Navamsha)
children          → D7 (Saptamsha)
wealth            → D2 (Hora) + D11 (Ekadashamsha)
health/longevity  → D3 (Drekkana) + D30 (Trimsamsha)
spirituality      → D20 (Vimshamsha) + D24 (Chaturvimshamsha)
property          → D4 (Chaturthamsha)
default           → D9 always
"""

from __future__ import annotations

from vedic_astro.agents.base import AgentInput, BaseAgent
from vedic_astro.settings import settings


_TOPIC_VARGAS: dict[str, list[int]] = {
    "career":       [10],
    "job":          [10],
    "profession":   [10],
    "business":     [10],
    "marriage":     [9],
    "partner":      [9],
    "spouse":       [9],
    "relationship": [9],
    "children":     [7],
    "child":        [7],
    "wealth":       [2],
    "money":        [2],
    "finance":      [2],
    "health":       [3, 30],
    "disease":      [3, 30],
    "longevity":    [3, 30],
    "spirituality": [20, 24],
    "spiritual":    [20, 24],
    "property":     [4],
    "home":         [4],
    "house":        [4],
}


def select_vargas(query: str) -> list[int]:
    """Return division numbers relevant to the query topic."""
    query_lower = query.lower()
    for keyword, divisions in _TOPIC_VARGAS.items():
        if keyword in query_lower:
            # Always include D9 alongside the selected
            result = [9] + [d for d in divisions if d != 9]
            return result
    return [9]  # Navamsha is always relevant


class DivisionalAgent(BaseAgent):
    """Interprets divisional charts relevant to the user query."""

    name = "divisional"
    system_prompt = (
        "You are a Vedic astrology specialist in divisional (Varga) charts. "
        "Focus on D9 (Navamsha) as the primary Varga, and any query-specific Varga. "
        "In D9: report lagna lord, atmakaraka placement, benefic/malefic influences. "
        "Compare with natal (D1) to assess if natal promise is fulfilled. "
        "One paragraph, max 4 sentences. Be concrete — name planets and signs."
    )

    @property
    def model(self) -> str:
        return settings.divisional_agent_model

    @property
    def max_tokens(self) -> int:
        return settings.divisional_agent_max_tokens

    def build_user_prompt(self, inp: AgentInput) -> str:
        data = inp.engine_data
        relevant_vargas = select_vargas(inp.query)
        rules_block = ""
        if inp.retrieved_rules:
            rules_block = "\n\nClassical Varga rules:\n" + "\n".join(
                f"- {r}" for r in inp.retrieved_rules[:4]
            )

        return (
            f"Query: {inp.query}\n"
            f"Relevant divisions: D{', D'.join(str(v) for v in relevant_vargas)}\n\n"
            f"Divisional Chart Data:\n{data}\n"
            f"{rules_block}\n\n"
            "Write a focused divisional chart interpretation."
        )
