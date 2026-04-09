"""
master_agent.py — Master prediction agent.

Aggregates all specialist agent narratives (Parashari + Jaimini + special lagnas
+ full varga set) using per-layer weights, applies Vedic cross-chart interaction
rules, and produces a single weighted prediction with an explicit confidence score.

Weight tuning: `ChartWeights` from `chart_weights.py` is passed in at call time.
Calibration in `calibration.py` adjusts these weights after comparing model
predictions with the user's confirmed life events.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from vedic_astro.learning.chart_weights import ChartWeights, weights_for_domain
from vedic_astro.tools.llm_client import get_llm_client
from vedic_astro.settings import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Cross-chart Vedic interaction rules (injected into the master prompt)
# ─────────────────────────────────────────────────────────────────────────────

_CROSS_CHART_RULES = """\
Cross-chart interaction rules (apply in your synthesis):
1. D1 promise vs D9 confirmation: A yoga in D1 is reliable only if the D9 also shows strength
   for the same planets/houses. D1 alone = potential; D1 + D9 = near-certain.
2. Dasha lord in D10/D9: If the Mahadasha lord is strong in the relevant divisional chart
   (D10 for career, D9 for marriage), the dasha delivers its promise fully.
3. Arudha Lagna vs Lagna: AL shows public reality; Lagna shows inner experience.
   A gap means private and public life differ significantly — mention this.
4. Chara Dasha confirmation: If Vimshottari Dasha and Jaimini Chara Dasha both activate
   the same planet/sign, the prediction carries double weight.
5. Argala amplification: Strong argalas (2nd, 4th, 11th) on the query house amplify the
   house's significations. Counter-argalas reduce them.
6. Karakamsha priority: For soul-level or purpose questions, Karakamsha sign and its
   lord override the D1 reading as the primary predictor.
7. Transit over sensitive Arudhas: Slow transits (Jupiter, Saturn, Rahu) over AL or
   A10 indicate major shifts in public/career reality even if D1 is static.
8. Rasi Drishti confirmation: A Jaimini Rasi aspect to the query house from a relevant
   karaka confirms the Parashari reading; absence weakens it.
"""

_SYSTEM = (
    "You are the master Vedic astrology prediction engine. "
    "You receive weighted narratives from eight specialist agents covering different "
    "chart layers: D1 natal, D9 Navamsha, other Vargas, Vimshottari Dasha, Gochara transit, "
    "Yogas/Doshas, Special Lagnas + Arudha Padas, and the Jaimini system. "
    "Each narrative is prefixed with its layer name and weight (e.g. '[D1 natal | 20%]'). "
    "Higher-weight layers carry more predictive authority for this query.\n\n"
    + _CROSS_CHART_RULES
    + "\n\n"
    "OUTPUT FORMAT:\n"
    "1. Confidence score: X.XX/1.00 (weighted average of layer agreement).\n"
    "2. Primary prediction (2-3 sentences): what the majority of weighted layers say.\n"
    "3. Confirming layers: which high-weight charts agree.\n"
    "4. Dissenting layers: which charts give a different signal and why.\n"
    "5. Net verdict: the most likely outcome given cross-chart consensus.\n"
    "6. Timing: Vimshottari + Chara Dasha combined timeline for activation.\n"
    "7. Recommended action: one concrete step for the next 3 months.\n"
    "Max 400 words. Name planets, signs, and houses concretely."
)


# ─────────────────────────────────────────────────────────────────────────────
# Input / Output
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MasterInput:
    query: str
    domain: str
    chart_id: str
    # Agent narratives keyed by layer name matching ChartWeights keys
    agent_narratives: dict[str, str]
    weights: ChartWeights
    # Optional classical rules for the master agent to check against
    classical_rules: list[str] = None

    def __post_init__(self):
        if self.classical_rules is None:
            self.classical_rules = []


@dataclass
class MasterOutput:
    narrative: str
    confidence: float                   # 0.0–1.0 extracted from narrative or estimated
    layer_contributions: dict[str, float]  # layer → weight used
    tokens_used: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────────────────────────────────────

class MasterAgent:
    """
    Aggregates all specialist narratives into a single weighted prediction.

    This agent runs AFTER all specialist agents have completed. It:
    1. Formats each narrative with its normalised weight label.
    2. Injects cross-chart interaction rules.
    3. Calls the LLM to produce a weighted cross-chart verdict.
    4. Extracts the confidence score from the output.
    """

    # Layer display names for the prompt
    _LAYER_LABELS: dict[str, str] = {
        "d1_natal":       "D1 Natal (Rasi Chart)",
        "d9_navamsha":    "D9 Navamsha (Soul/Spouse)",
        "d10_dasamsa":    "D10 Dasamsha (Career/Profession)",
        "vimshottari":    "Vimshottari Dasha (Maha+Antar timing)",
        "transit":        "Gochara Transit (Current activation)",
        "yogas":          "Yogas & Doshas (Combinations)",
        "special_lagnas": "Special Lagnas & Arudha Padas",
        "arudha_padas":   "Arudha Padas (External reality)",
        "jaimini":        "Jaimini System (Chara Karakas + Dasha)",
        "other_vargas":   "Other Divisional Charts (D2–D60)",
    }

    def __init__(self) -> None:
        self._llm = get_llm_client()

    async def run(self, inp: MasterInput) -> MasterOutput:
        norm_weights = inp.weights.normalised

        # Build the weighted narratives block
        narrative_blocks: list[str] = []
        for layer, narrative in inp.agent_narratives.items():
            if not narrative:
                continue
            weight_pct = int(round(norm_weights.get(layer, 0.0) * 100))
            label = self._LAYER_LABELS.get(layer, layer)
            narrative_blocks.append(
                f"[{label} | {weight_pct}%]\n{narrative}"
            )

        rules_block = ""
        if inp.classical_rules:
            rules_block = "\n\nClassical rules to verify against:\n" + "\n".join(
                f"- {r}" for r in inp.classical_rules[:6]
            )

        user = (
            f"User query: {inp.query}\n"
            f"Domain: {inp.domain}\n\n"
            "=== WEIGHTED SPECIALIST NARRATIVES ===\n"
            + "\n\n".join(narrative_blocks)
            + rules_block
            + "\n\n"
            "Produce the master prediction following the output format above."
        )

        raw = await self._llm.complete(
            system=_SYSTEM,
            user=user,
            model=settings.synthesis_model,
            max_tokens=600,
            temperature=0.3,
        )

        confidence = self._extract_confidence(raw)
        return MasterOutput(
            narrative=raw.strip(),
            confidence=confidence,
            layer_contributions={k: norm_weights.get(k, 0.0) for k in inp.agent_narratives},
        )

    @staticmethod
    def _extract_confidence(text: str) -> float:
        """Parse the confidence score from the master narrative (e.g. '0.72/1.00')."""
        import re
        m = re.search(r"(\d+\.\d+)\s*/\s*1\.0+", text)
        if m:
            try:
                return min(1.0, max(0.0, float(m.group(1))))
            except ValueError:
                pass
        return 0.5   # default if not parseable


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: build MasterInput from PipelineState
# ─────────────────────────────────────────────────────────────────────────────

def build_master_input(
    state,                         # PipelineState (typed loosely to avoid circular import)
    query: str,
    domain: str,
    weights: Optional[ChartWeights] = None,
) -> MasterInput:
    """
    Assemble a MasterInput from a fully-computed PipelineState.

    Maps PipelineState.agent_outputs keys to ChartWeights layer names.
    """
    if weights is None:
        weights = weights_for_domain(domain)

    # Map existing agent output names to weight layer names
    key_map = {
        "natal":         "d1_natal",
        "divisional":    "d9_navamsha",    # primary divisional narrative covers D9
        "dasha":         "vimshottari",
        "transit":       "transit",
        "yoga":          "yogas",
        "special_lagna": "special_lagnas",
        "jaimini":       "jaimini",
    }

    narratives: dict[str, str] = {}
    for agent_key, layer_key in key_map.items():
        narratives[layer_key] = state.agent_outputs.get(agent_key, "")

    all_rules = [r for rules in state.retrieved_rules.values() for r in rules]

    return MasterInput(
        query=query,
        domain=domain,
        chart_id=state.chart_id,
        agent_narratives=narratives,
        weights=weights,
        classical_rules=all_rules,
    )
