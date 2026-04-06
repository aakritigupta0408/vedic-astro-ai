"""
output_formatter.py — Structured reading output with reasoning chain and citations.

Output schema
-------------
Every pipeline run produces a ``StructuredReading`` that contains:

1. ``reasoning_chain``   — Ordered steps (natal→dasha→transit→divisional→yoga)
                           with finding text, layer weight, and component score.
2. ``weighted_summary``  — One paragraph tying all layers together with explicit
                           weights stated in prose ("natal foundation [35%] shows…")
3. ``supporting_quotes`` — Direct citations from classical texts retrieved by RAG,
                           formatted as:
                               Quote: "<verbatim rule text>"
                               Source: "<text name + chapter/verse>"
4. ``final_reading``     — The full synthesised narrative (from SynthesisAgent,
                           optionally revised by ReviserAgent).
5. ``score``             — WeightedScorer ScoreBreakdown.
6. ``critic_notes``      — Issues identified by CriticAgent (empty if passed).
7. ``was_revised``       — Whether ReviserAgent was triggered.

The formatter receives all agent outputs and the pipeline state; it does NOT
make any LLM calls.

Usage
-----
    formatter = OutputFormatter()
    reading = formatter.format(
        query=..., agent_outputs=..., synthesis=..., score=...,
        retrieved_rules=..., critic_result=..., final_reading=...
    )
    print(reading.to_markdown())
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from vedic_astro.learning.scorer import ScoreBreakdown


# ─────────────────────────────────────────────────────────────────────────────
# Sub-schemas
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReasoningStep:
    """One layer of the astrological analysis."""
    step:        str          # "natal" | "dasha" | "transit" | "divisional" | "yoga"
    label:       str          # human-readable label
    finding:     str          # the agent's narrative for this layer
    weight_pct:  int          # global layer weight as percentage (35, 30, 25, 10…)
    component_score: float    # 0.0–1.0 score from WeightedScorer for this layer
    key_factors: list[str]    # bullet-point key factors

    @property
    def score_label(self) -> str:
        s = self.component_score
        if s >= 0.75: return "★★★★★"
        if s >= 0.60: return "★★★★☆"
        if s >= 0.45: return "★★★☆☆"
        if s >= 0.30: return "★★☆☆☆"
        return "★☆☆☆☆"


@dataclass
class Quote:
    """A direct citation from a classical text."""
    text:      str    # verbatim rule text
    source:    str    # "BPHS Chapter 12, Verse 5"
    relevance: str    # one phrase explaining why this applies


@dataclass
class StructuredReading:
    """
    Complete structured reading output.

    All fields are populated by ``OutputFormatter.format()`` — no field
    should ever be None in a complete reading.
    """
    chart_id:          str
    query:             str
    reasoning_chain:   list[ReasoningStep]
    weighted_summary:  str
    supporting_quotes: list[Quote]
    final_reading:     str
    score:             ScoreBreakdown
    critic_notes:      list[str]
    was_revised:       bool

    # Evidence for UI panels
    natal_narrative:       str = ""
    dasha_narrative:       str = ""
    transit_narrative:     str = ""
    divisional_narrative:  str = ""
    yoga_narrative:        str = ""
    retrieved_rules:       dict[str, list[str]] = field(default_factory=dict)
    retrieved_cases:       list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render the full reading as Markdown for the Gradio chat panel.

        Leads with the quantitative score table and formula so the answer
        is deterministic and auditable before the narrative explanation.
        """
        domain_title = self.score.domain.replace("_", " ").title()
        interp_label = self.score.interpretation.replace("_", " ").title()

        lines = [
            f"## {domain_title} Score: {self.score.final_score:.3f} / 1.000 — {interp_label}",
            "",
            "### Weighted Score Breakdown",
            "",
            self.score.score_table_md,
            "",
            f"**Formula:** {self.score.formula}",
            "",
            "---",
            "### Analysis",
            "",
            self.final_reading,
        ]

        if self.weighted_summary:
            lines += [
                "",
                "---",
                "### Layer-by-Layer Reasoning",
                "",
                self.weighted_summary,
            ]

        if self.supporting_quotes:
            lines += ["", "---", "### Classical References", ""]
            for q in self.supporting_quotes[:3]:
                lines += [
                    f"> \"{q.text}\"",
                    f"> — *{q.source}* ({q.relevance})",
                    "",
                ]

        if self.was_revised:
            lines += ["", "*Reading was refined after quality review.*"]

        return "\n".join(lines)

    def to_debug_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict for the debug panel."""
        return {
            "chart_id": self.chart_id,
            "score": {
                "final": self.score.final_score,
                "formula": self.score.formula,
                "natal": self.score.natal_strength,
                "natal_d1": self.score.d1_strength,
                "natal_d9_navamsha": self.score.navamsha_strength,
                "dasha": self.score.dasha_activation,
                "transit": self.score.transit_trigger,
                "yoga": self.score.yoga_support,
                "dosha_penalty": self.score.dosha_penalty,
                "interpretation": self.score.interpretation,
                "weights_used": self.score.weights_used,
            },
            "was_revised": self.was_revised,
            "critic_notes": self.critic_notes,
            "reasoning_steps": [
                {
                    "step": s.step,
                    "weight_pct": s.weight_pct,
                    "score": s.component_score,
                    "key_factors": s.key_factors,
                }
                for s in self.reasoning_chain
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Quote extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_source(rule_text: str) -> tuple[str, str]:
    """
    Split a rule string ``"<text> [<source>]"`` into (text, source).

    Returns (rule_text, "") if no bracket source found.
    """
    m = re.search(r"\[([^\]]+)\]\s*$", rule_text)
    if m:
        text = rule_text[:m.start()].strip()
        source = m.group(1).strip()
        return text, source
    return rule_text, ""


def _select_quotes(
    retrieved_rules: dict[str, list[str]],
    reasoning_chain: list[ReasoningStep],
    max_quotes: int = 4,
) -> list[Quote]:
    """
    Pick the most relevant rules from RAG results and format as Quote objects.

    Selection strategy:
    - Prefer rules from high-weight layers (natal and dasha first).
    - At most 2 per layer.
    - Skip rules that are too short (< 30 chars) to be meaningful.
    """
    _RELEVANCE_LABELS = {
        "natal":      "confirms natal chart promise",
        "dasha":      "applies to the active dasha period",
        "transit":    "applies to current transits",
        "divisional": "validates divisional chart reading",
        "yoga":       "describes the active yoga combination",
    }

    quotes: list[Quote] = []
    seen: set[str] = set()
    # Order layers by weight (descending)
    ordered_steps = sorted(reasoning_chain, key=lambda s: s.weight_pct, reverse=True)

    for step in ordered_steps:
        if len(quotes) >= max_quotes:
            break
        rules = retrieved_rules.get(step.step, [])
        added = 0
        for raw_rule in rules:
            if added >= 2 or len(quotes) >= max_quotes:
                break
            text, source = _parse_source(raw_rule)
            if len(text) < 30 or text in seen:
                continue
            seen.add(text)
            quotes.append(Quote(
                text=text,
                source=source or "Classical text",
                relevance=_RELEVANCE_LABELS.get(step.step, "relevant to query"),
            ))
            added += 1

    return quotes


# ─────────────────────────────────────────────────────────────────────────────
# Weighted summary builder
# ─────────────────────────────────────────────────────────────────────────────

_SCORE_ADJECTIVES: dict[str, str] = {
    "very_strong_positive": "very strong",
    "strong_positive":      "strong",
    "moderate_positive":    "moderate",
    "mixed":                "mixed",
    "challenging":          "challenging",
    "very_challenging":     "very challenging",
}


def _build_weighted_summary(
    reasoning_chain: list[ReasoningStep],
    score: ScoreBreakdown,
    domain: str,
) -> str:
    """
    Build a weighted layer-by-layer summary from reasoning steps.

    Each layer shows its weight, numeric score, and the first sentence of
    the agent's finding, so the reader can see exactly what drove the score.
    """
    parts = []
    for step in reasoning_chain:
        if not step.finding:
            continue
        # Take first sentence of finding
        first_sentence = re.split(r"(?<=[.!?])\s+", step.finding.strip())[0]
        score_stars = step.score_label
        parts.append(
            f"**{step.label} [{step.weight_pct}%] · {step.component_score:.2f} {score_stars}**\n"
            f"{first_sentence}"
        )

    if score.notes:
        notable = [n for n in score.notes if n][:4]
        if notable:
            parts.append("**Key factors:**\n" + "\n".join(f"- {n}" for n in notable))

    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Formatter
# ─────────────────────────────────────────────────────────────────────────────

_STEP_LABELS: dict[str, tuple[str, int]] = {
    # step → (label, weight%)
    "natal":      ("Natal Foundation (D1)",          35),
    "dasha":      ("Vimshottari Dasha Timing",        30),
    "transit":    ("Gochara Transit Activation",      25),
    "divisional": ("Divisional Chart Refinement",     10),
    "yoga":       ("Yoga / Dosha Synthesis",           0),  # folded into natal weight
}


class OutputFormatter:
    """
    Assembles all pipeline outputs into a ``StructuredReading``.

    No LLM calls.  Pure data assembly.
    """

    def format(
        self,
        chart_id: str,
        query: str,
        domain: str,
        agent_outputs: dict[str, str],     # step → narrative text
        synthesis: str,
        final_reading: str,
        score: ScoreBreakdown,
        retrieved_rules: dict[str, list[str]],
        retrieved_cases: list[str],
        critic_notes: list[str],
        was_revised: bool,
    ) -> StructuredReading:
        """
        Build a ``StructuredReading`` from all pipeline outputs.

        Parameters
        ----------
        agent_outputs : dict mapping step name to narrative string.
                        Keys: "natal", "dasha", "transit", "divisional", "yoga".
        synthesis     : Raw synthesis narrative before any revision.
        final_reading : The reading returned to the user (may be revised).
        """
        # ── Reasoning chain ───────────────────────────────────────────────
        reasoning_chain: list[ReasoningStep] = []
        step_scores = {
            "natal":      score.natal_strength,
            "dasha":      score.dasha_activation,
            "transit":    score.transit_trigger,
            "divisional": 0.5,   # no separate divisional score in ScoreBreakdown
            "yoga":       score.yoga_support,
        }

        for step in ["natal", "dasha", "transit", "divisional", "yoga"]:
            narrative = agent_outputs.get(step, "")
            if not narrative:
                continue
            label, weight_pct = _STEP_LABELS[step]
            key_factors = self._extract_key_factors(narrative)
            reasoning_chain.append(ReasoningStep(
                step=step,
                label=label,
                finding=narrative,
                weight_pct=weight_pct,
                component_score=step_scores.get(step, 0.5),
                key_factors=key_factors,
            ))

        # ── Weighted summary ──────────────────────────────────────────────
        weighted_summary = _build_weighted_summary(reasoning_chain, score, domain)

        # ── Quotes ────────────────────────────────────────────────────────
        supporting_quotes = _select_quotes(retrieved_rules, reasoning_chain)

        return StructuredReading(
            chart_id=chart_id,
            query=query,
            reasoning_chain=reasoning_chain,
            weighted_summary=weighted_summary,
            supporting_quotes=supporting_quotes,
            final_reading=final_reading,
            score=score,
            critic_notes=critic_notes,
            was_revised=was_revised,
            natal_narrative=agent_outputs.get("natal", ""),
            dasha_narrative=agent_outputs.get("dasha", ""),
            transit_narrative=agent_outputs.get("transit", ""),
            divisional_narrative=agent_outputs.get("divisional", ""),
            yoga_narrative=agent_outputs.get("yoga", ""),
            retrieved_rules=retrieved_rules,
            retrieved_cases=retrieved_cases,
        )

    @staticmethod
    def _extract_key_factors(text: str) -> list[str]:
        """Extract up to 4 key sentences from a narrative paragraph."""
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        return [s.strip() for s in sentences if len(s.strip()) > 25][:4]
