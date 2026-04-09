"""
jaimini_agent.py — Specialist agent for Jaimini system interpretation.
"""

from __future__ import annotations

from vedic_astro.agents.base import AgentInput, BaseAgent
from vedic_astro.settings import settings


class JaiminiAgent(BaseAgent):
    """
    Interprets Jaimini Chara Karakas, Karakamsha, Chara Dasha, Rasi Drishti,
    and Argalas. Complements the Parashari Vimshottari reading with a
    Jaimini-system perspective on the same chart.
    """

    name = "jaimini"
    system_prompt = (
        "You are a Vedic astrology specialist in the Jaimini system. "
        "Jaimini uses sign aspects (Rasi Drishti), Chara Karakas (moving significators), "
        "and Chara Dasha (sign-based timing) instead of Parashari nakshatra-based timing. "
        "Key Karakas: "
        "Atmakaraka (AK) = soul's purpose; "
        "Amatyakaraka (AmK) = career/advice; "
        "Darakaraka (DK) = spouse/partner; "
        "Putrakaraka (PK) = children/creativity; "
        "Gnatikaraka (GK) = health/competition. "
        "Karakamsha = AK's D9 sign = the domain of soul's fullest expression. "
        "Chara Dasha = active sign dasha showing current life chapter. "
        "Report: active Chara Dasha sign + lord, AK and relevant karaka for query, "
        "Karakamsha sign, any strong argalas on the lagna or query house. "
        "One paragraph, max 5 sentences. Name planets and signs concretely."
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
            rules_block = "\n\nJaimini classical rules:\n" + "\n".join(
                f"- {r}" for r in inp.retrieved_rules[:4]
            )

        # Pick relevant karaka for the query domain
        query_lower = inp.query.lower()
        if any(w in query_lower for w in ("career", "job", "profession", "business")):
            focal_karaka = "Amatyakaraka (AmK) for career"
        elif any(w in query_lower for w in ("marriage", "spouse", "partner", "relationship")):
            focal_karaka = "Darakaraka (DK) for partner"
        elif any(w in query_lower for w in ("children", "child")):
            focal_karaka = "Putrakaraka (PK) for children"
        elif any(w in query_lower for w in ("health", "disease", "illness")):
            focal_karaka = "Gnatikaraka (GK) for health"
        elif any(w in query_lower for w in ("spiritual", "soul", "purpose")):
            focal_karaka = "Atmakaraka (AK) for soul purpose"
        else:
            focal_karaka = "Atmakaraka (AK) and Amatyakaraka (AmK)"

        return (
            f"Query: {inp.query}\n"
            f"Focal Karaka for this query: {focal_karaka}\n\n"
            f"Jaimini System Data:\n{data}\n"
            f"{rules_block}\n\n"
            "Interpret through the Jaimini lens: karakas, Chara Dasha, argalas."
        )
