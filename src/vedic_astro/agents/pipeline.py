"""
pipeline.py — Deterministic astrological pipeline.

Stages: geocode → chart → dasha/transit/vargas (parallel) → yogas →
        shadbala → features → score → RAG → specialist agents (parallel) →
        synthesis → conditional critic/reviser → format.

Usage:
    runner = PipelineRunner()
    state  = await runner.compute_chart(request)   # Phase 1, no LLM
    reading = await runner.predict(state, query)    # Phase 3, LLM
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional, TYPE_CHECKING

from vedic_astro.agents.output_formatter import OutputFormatter, StructuredReading
from vedic_astro.settings import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Request / State
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BirthData:
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int = 0
    place: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    timezone_str: str = "UTC"


@dataclass
class ReadingRequest:
    birth: BirthData
    query: str
    query_date: Optional[date] = None
    domain: str = "general"          # career|marriage|wealth|health|general
    depth: int = 2                   # dasha depth (2=maha+antar)


@dataclass
class PipelineState:
    """Accumulates results as each stage completes. Passed between stages."""
    request: ReadingRequest

    # Stage outputs (None until stage completes)
    chart: Any = None                      # NatalChart
    dasha_window: Any = None               # DashaWindow
    transit_overlay: Any = None            # TransitOverlay
    varga_charts: dict = field(default_factory=dict)
    special_lagna_bundle: Any = None       # SpecialLagnaBundle
    jaimini_bundle: Any = None             # JaiminiBundle
    yoga_bundle: Any = None                # YogaDoshaBundle
    shadbala: Any = None                   # dict[str, ShadbalaScore]
    features: Any = None                   # AstroFeatures
    score: Any = None                      # ScoreBreakdown
    chart_weights: Any = None              # ChartWeights (calibration-tuned)

    # RAG
    retrieved_rules: dict[str, list[str]] = field(default_factory=dict)
    retrieved_cases: list[str] = field(default_factory=list)

    # LLM narratives
    agent_outputs: dict[str, str] = field(default_factory=dict)
    master_output: Any = None              # MasterOutput
    synthesis_raw: str = ""
    critic_result: Any = None
    final_reading: str = ""

    # Meta
    chart_id: str = ""
    stages_completed: list[str] = field(default_factory=list)

    def mark_done(self, stage: str) -> None:
        if stage not in self.stages_completed:
            self.stages_completed.append(stage)

    @property
    def query_date(self) -> date:
        return self.request.query_date or date.today()


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline runner
# ─────────────────────────────────────────────────────────────────────────────

class PipelineRunner:
    """
    Deterministic pipeline coordinator.

    Each public stage method:
    - Accepts a ``PipelineState`` and mutates it in place.
    - Is idempotent (skips if output already populated).
    - Logs its duration for observability.
    """

    def __init__(self) -> None:
        self._formatter = OutputFormatter()
        self._natal_agent = None
        self._dasha_agent = None
        self._transit_agent = None
        self._divisional_agent = None
        self._special_lagna_agent = None
        self._jaimini_agent = None
        self._yoga_agent = None
        self._synthesis = None
        self._master_agent = None
        self._critic = None
        self._reviser = None

    def _lazy_init_agents(self) -> None:
        """Lazy-init agents to avoid import cost when not needed."""
        if self._natal_agent is not None:
            return
        from vedic_astro.agents.natal_agent import NatalAgent
        from vedic_astro.agents.dasha_agent import DashaAgent
        from vedic_astro.agents.transit_agent import TransitAgent
        from vedic_astro.agents.divisional_agent import DivisionalAgent
        from vedic_astro.agents.special_lagna_agent import SpecialLagnaAgent
        from vedic_astro.agents.jaimini_agent import JaiminiAgent
        from vedic_astro.agents.synthesis_agent import SynthesisAgent
        from vedic_astro.agents.master_agent import MasterAgent
        from vedic_astro.agents.critic_agent import CriticAgent
        from vedic_astro.agents.reviser_agent import ReviserAgent
        from vedic_astro.agents.solver_agent import YogaAgent

        self._natal_agent = NatalAgent()
        self._dasha_agent = DashaAgent()
        self._transit_agent = TransitAgent()
        self._divisional_agent = DivisionalAgent()
        self._special_lagna_agent = SpecialLagnaAgent()
        self._jaimini_agent = JaiminiAgent()
        self._yoga_agent = YogaAgent()
        self._synthesis = SynthesisAgent()
        self._master_agent = MasterAgent()
        self._critic = CriticAgent()
        self._reviser = ReviserAgent()

    # ── Phase 1: compute chart (no LLM, no question needed) ──────────────

    async def compute_chart(self, request: ReadingRequest) -> "PipelineState":
        """Phase 1 — run all deterministic engine stages, no LLM calls."""
        state = PipelineState(request=request)
        import time
        t0 = time.monotonic()

        await self.stage_geocode(state)
        await self.stage_chart(state)
        await asyncio.gather(
            self.stage_dasha(state),
            self.stage_transit(state),
            self.stage_vargas(state),
        )
        # Special lagnas and Jaimini can run once vargas are done (need D9 data)
        await asyncio.gather(
            self.stage_special_lagnas(state),
            self.stage_jaimini(state),
            self.stage_yogas(state),
        )
        await self.stage_shadbala(state)
        self.stage_features(state)
        self.stage_score(state)

        elapsed = time.monotonic() - t0
        logger.info(
            "Phase 1 complete: chart=%s elapsed=%.1fs",
            state.chart_id[:8] if state.chart_id else "?", elapsed,
        )
        return state

    # ── Phase 3: predict (LLM synthesis on pre-computed state) ───────────

    async def predict(
        self,
        state: "PipelineState",
        query: str,
        domain: str = "general",
        calibration_weights: Optional[dict] = None,
    ) -> StructuredReading:
        """Phase 3 — run LLM agents on a pre-computed PipelineState."""
        import time
        t0 = time.monotonic()

        # Inject query + domain into state
        state.request.query  = query
        state.request.domain = domain

        # Initialise chart weights (domain-aware defaults, then apply calibration)
        from vedic_astro.learning.chart_weights import weights_for_domain
        if state.chart_weights is None:
            state.chart_weights = weights_for_domain(domain)
        if calibration_weights:
            # Apply calibration adjustments on top of domain defaults
            for layer, delta in calibration_weights.get("layer_deltas", {}).items():
                state.chart_weights.adjust(layer, delta)

        # Re-score with calibrated weights if provided
        if calibration_weights and state.features:
            from vedic_astro.learning.scorer import WeightedScorer, ScoringWeights
            cal_w = calibration_weights
            w = ScoringWeights(
                natal_weight=cal_w.get("natal",   0.20),
                dasha_weight=cal_w.get("dasha",   0.30),
                transit_weight=cal_w.get("transit", 0.20),
                yoga_weight=cal_w.get("yoga",     0.20),
                dosha_weight=cal_w.get("dosha",   0.10),
            )
            state.score = WeightedScorer(weights=w).score(state.features, domain=domain)

        # Clear any previous LLM outputs so agents re-run with new query
        state.agent_outputs  = {}
        state.synthesis_raw  = ""
        state.final_reading  = ""
        state.critic_result  = None
        state.retrieved_rules = {}
        state.retrieved_cases = []

        await self.stage_rag(state)
        self._lazy_init_agents()
        await self.stage_solve(state)
        await self.stage_synthesise(state)
        await self.stage_critique_and_revise(state)
        reading = self.stage_format(state)

        elapsed = time.monotonic() - t0
        logger.info(
            "Phase 3 complete: chart=%s query=%r elapsed=%.1fs",
            state.chart_id[:8] if state.chart_id else "?", query[:40], elapsed,
        )
        return reading

    # ── Main entry point (backward-compatible single call) ────────────────

    async def run(self, request: ReadingRequest) -> StructuredReading:
        """
        Run the full pipeline in one call (backward-compatible).
        Internally calls compute_chart() then predict().
        """
        state = await self.compute_chart(request)
        return await self.predict(state, request.query, request.domain)

    # ── Stage: geocode ────────────────────────────────────────────────────

    async def stage_geocode(self, state: PipelineState) -> None:
        b = state.request.birth
        if b.lat is not None and b.lon is not None:
            state.mark_done("geocode")
            return
        if not b.place:
            raise ValueError("Provide either lat/lon or place name.")
        from vedic_astro.tools.geo import get_geo_resolver
        loc = await get_geo_resolver().resolve(b.place)
        b.lat, b.lon, b.timezone_str = loc.lat, loc.lon, loc.timezone
        state.mark_done("geocode")
        logger.debug("Geocoded %r → %.4f, %.4f (%s)", b.place, b.lat, b.lon, b.timezone_str)

    # ── Stage: chart ──────────────────────────────────────────────────────

    async def stage_chart(self, state: PipelineState) -> None:
        if state.chart is not None:
            return
        b = state.request.birth
        from vedic_astro.engines.natal_engine import build_natal_chart
        import pytz
        dob = date(b.year, b.month, b.day)
        try:
            tz = pytz.timezone(b.timezone_str or "UTC")
            tob_local = tz.localize(datetime(b.year, b.month, b.day, b.hour, b.minute, b.second))
            tob_utc = tob_local.astimezone(pytz.utc)
        except Exception as exc:
            logger.warning("Timezone %r parse failed (%s); falling back to UTC", b.timezone_str, exc)
            tob_utc = datetime(b.year, b.month, b.day, b.hour, b.minute, b.second,
                               tzinfo=pytz.utc)
        state.chart = await asyncio.to_thread(
            build_natal_chart,
            dob, tob_utc, b.lat, b.lon,
        )
        state.chart_id = state.chart.chart_id
        state.mark_done("chart")
        logger.debug("Chart built: %s", state.chart_id[:8])

    # ── Stage: dasha ──────────────────────────────────────────────────────

    async def stage_dasha(self, state: PipelineState) -> None:
        if state.dasha_window is not None:
            return
        if state.chart is None:
            return
        b = state.request.birth
        from vedic_astro.engines.dasha_engine import get_active_dasha_window
        from vedic_astro.engines.natal_engine import PlanetName
        moon_lon  = state.chart.planets[PlanetName.MOON].longitude
        birth_dt  = date(b.year, b.month, b.day)
        state.dasha_window = await asyncio.to_thread(
            get_active_dasha_window,
            moon_lon, birth_dt, state.query_date, state.chart,
            state.request.depth,
        )
        state.mark_done("dasha")

    # ── Stage: transit ────────────────────────────────────────────────────

    async def stage_transit(self, state: PipelineState) -> None:
        if state.transit_overlay is not None:
            return
        if state.chart is None:
            return
        from vedic_astro.engines.transit_engine import (
            compute_transit_snapshot, compute_transit_overlay
        )
        snapshot = await asyncio.to_thread(compute_transit_snapshot, state.query_date)
        state.transit_overlay = await asyncio.to_thread(
            compute_transit_overlay, snapshot, state.chart
        )
        state.mark_done("transit")

    # ── Stage: vargas ─────────────────────────────────────────────────────

    async def stage_vargas(self, state: PipelineState) -> None:
        if state.varga_charts:
            return
        if state.chart is None:
            return
        from vedic_astro.engines.varga_engine import compute_required_charts
        # Compute a comprehensive set of divisional charts: D1-D12, D16, D20, D24, D27, D30, D40, D45, D60
        # plus domain-specific ones — all available from the varga engine
        all_divisions = list({
            1, 2, 3, 4, 7, 9, 10, 12, 16, 20, 24, 27, 30, 40, 45, 60,
            *self._domain_vargas(state.request.domain),
        })
        state.varga_charts = await asyncio.to_thread(
            compute_required_charts,
            state.chart, all_divisions,
            skip_on_precision_error=True,
        )
        state.mark_done("vargas")

    async def stage_special_lagnas(self, state: PipelineState) -> None:
        """Compute special lagnas, arudha padas, and alternate chart frames."""
        if state.special_lagna_bundle is not None:
            return
        if state.chart is None:
            return
        try:
            from vedic_astro.engines.special_lagna_engine import compute_special_lagna_bundle
            from vedic_astro.engines.natal_engine import PlanetName

            # Extract D9 planet positions if available
            d9_planets: dict[PlanetName, int] = {}
            if 9 in state.varga_charts:
                d9 = state.varga_charts[9]
                d9_planets = {p: pos.sign_number for p, pos in d9.planets.items()}

            b = state.request.birth
            birth_hour_decimal = b.hour + b.minute / 60.0 + b.second / 3600.0

            state.special_lagna_bundle = await asyncio.to_thread(
                compute_special_lagna_bundle,
                state.chart, d9_planets, birth_hour_decimal,
            )
            state.mark_done("special_lagnas")
        except Exception as exc:
            logger.warning("Special lagna computation failed: %s", exc)

    async def stage_jaimini(self, state: PipelineState) -> None:
        """Compute Jaimini chara karakas, rasi drishti, argalas, and chara dasha."""
        if state.jaimini_bundle is not None:
            return
        if state.chart is None:
            return
        try:
            from vedic_astro.engines.jaimini_engine import compute_jaimini_bundle
            from vedic_astro.engines.natal_engine import PlanetName

            d9_planets: dict[PlanetName, int] = {}
            if 9 in state.varga_charts:
                d9 = state.varga_charts[9]
                d9_planets = {p: pos.sign_number for p, pos in d9.planets.items()}

            b = state.request.birth
            birth_dt = date(b.year, b.month, b.day)

            state.jaimini_bundle = await asyncio.to_thread(
                compute_jaimini_bundle,
                state.chart, birth_dt, d9_planets, state.query_date,
            )
            state.mark_done("jaimini")
        except Exception as exc:
            logger.warning("Jaimini computation failed: %s", exc)

    async def stage_shadbala(self, state: PipelineState) -> None:
        """Compute Shadbala (six-fold planetary strength) for all planets."""
        if getattr(state, "shadbala", None) is not None:
            return
        if state.chart is None:
            return
        try:
            from vedic_astro.learning.shadbala import compute_shadbala
            from datetime import datetime
            b = state.request.birth
            birth_dt = datetime(b.year, b.month, b.day, b.hour, b.minute)
            state.shadbala = await asyncio.to_thread(compute_shadbala, state.chart, birth_dt)
            state.mark_done("shadbala")
        except Exception as exc:
            logger.warning("Shadbala computation failed: %s", exc)
            state.shadbala = {}

    @staticmethod
    def _domain_vargas(domain: str) -> list[int]:
        return {
            "career":       [10],
            "marriage":     [9, 7],
            "wealth":       [2],
            "health":       [3, 30],
            "spirituality": [20],
            "children":     [7],
        }.get(domain, [])

    # ── Stage: yogas ──────────────────────────────────────────────────────

    async def stage_yogas(self, state: PipelineState) -> None:
        if state.yoga_bundle is not None:
            return
        if state.chart is None:
            return
        from vedic_astro.engines.yoga_dosha_engine import detect_all_yogas_and_doshas
        state.yoga_bundle = await asyncio.to_thread(
            detect_all_yogas_and_doshas, state.chart
        )
        state.mark_done("yogas")

    # ── Stage: features + score ───────────────────────────────────────────

    def stage_features(self, state: PipelineState) -> None:
        if state.features is not None:
            return
        if state.chart is None:
            return
        from vedic_astro.learning.feature_builder import FeatureBuilder
        state.features = FeatureBuilder().build(
            chart=state.chart,
            dasha_window=state.dasha_window,
            transit_overlay=state.transit_overlay,
            varga_charts=state.varga_charts or {},
            yoga_bundle=state.yoga_bundle,
        )
        state.mark_done("features")

    def stage_score(self, state: PipelineState) -> None:
        if state.score is not None or state.features is None:
            return
        from vedic_astro.learning.scorer import WeightedScorer
        state.score = WeightedScorer().score(state.features, domain=state.request.domain)
        state.mark_done("score")

    # ── Stage: RAG ────────────────────────────────────────────────────────

    async def stage_rag(self, state: PipelineState) -> None:
        """
        Inject hardcoded BPHS rules + attempt RAG retrieval (graceful fallback).

        Hardcoded rules from bphs_rules.py are always available and selected
        per agent/domain. RAG retrieval from the vector store is attempted
        and merged if available, otherwise ignored.
        """
        if state.retrieved_rules:
            return

        domain = state.request.domain or "general"

        # 1. Select hardcoded BPHS rules for each agent
        try:
            from vedic_astro.rules.rule_selector import select_all_rules
            natal_data   = self._serialise_chart(state.chart)
            dasha_data   = self._serialise_dasha(state.dasha_window, state.features)
            transit_data = self._serialise_transit(state.transit_overlay, state.features)
            yoga_data    = self._serialise_yogas(state.yoga_bundle, state.score, state.features)
            bphs_rules = select_all_rules(natal_data, dasha_data, transit_data, yoga_data, domain)
        except Exception as exc:
            logger.debug("BPHS rule selection failed: %s", exc)
            bphs_rules = {}

        # 2. Attempt RAG retrieval (may be empty if index not built)
        async def get_rag_rules(domain_key: str, query_suffix: str) -> tuple[str, list[str]]:
            try:
                from vedic_astro.rag.rule_retriever import retrieve_rules_for_domain
                rules = await retrieve_rules_for_domain(
                    f"{state.request.query} {query_suffix}", domain_key, top_k=3
                )
                return domain_key, rules
            except Exception as exc:
                logger.debug("RAG rule retrieval failed for %s: %s", domain_key, exc)
                return domain_key, []

        async def get_cases() -> list[str]:
            try:
                from vedic_astro.rag.case_retriever import CaseRetriever
                maha = state.features.maha_lord if state.features else None
                return await CaseRetriever().retrieve(
                    state.chart, state.request.query, top_k=3, maha_lord=maha
                )
            except Exception as exc:
                logger.debug("RAG case retrieval failed: %s", exc)
                return []

        rag_results = await asyncio.gather(
            get_rag_rules("natal",      "natal chart planet house"),
            get_rag_rules("dasha",      "dasha period timing"),
            get_rag_rules("transit",    "gochara transit"),
            get_rag_rules("divisional", "varga divisional navamsha"),
            get_rag_rules("yoga",       "yoga dosha combination"),
            get_cases(),
        )

        # 3. Merge: BPHS rules first, then RAG additions
        for key, rag_rules in rag_results[:5]:
            hardcoded = bphs_rules.get(key, [])
            merged = hardcoded + [r for r in rag_rules if r not in hardcoded]
            state.retrieved_rules[key] = merged

        state.retrieved_cases = rag_results[5]
        state.mark_done("rag")

    # ── Stage: solve (parallel specialist agents) ─────────────────────────

    async def stage_solve(self, state: PipelineState) -> None:
        """Run all specialist agents concurrently — wall-clock ≈ 1 LLM call."""
        if state.agent_outputs:
            return

        from vedic_astro.agents.base import AgentInput

        def _make_input(step: str, engine_data: Any) -> AgentInput:
            return AgentInput(
                chart_id=state.chart_id,
                query=state.request.query,
                engine_data=engine_data,
                retrieved_rules=state.retrieved_rules.get(step, []),
                retrieved_cases=state.retrieved_cases if step == "natal" else [],
            )

        natal_data        = self._serialise_chart(state.chart)
        dasha_data        = self._serialise_dasha(state.dasha_window, state.features)
        transit_data      = self._serialise_transit(state.transit_overlay, state.features)
        varga_data        = self._serialise_vargas(state.varga_charts)
        yoga_data         = self._serialise_yogas(state.yoga_bundle, state.score, state.features)
        special_data      = self._serialise_special_lagnas(state.special_lagna_bundle)
        jaimini_data      = self._serialise_jaimini(state.jaimini_bundle)

        agents_and_inputs = [
            ("natal",         self._natal_agent,         _make_input("natal", natal_data)),
            ("dasha",         self._dasha_agent,         _make_input("dasha", dasha_data)),
            ("transit",       self._transit_agent,       _make_input("transit", transit_data)),
            ("divisional",    self._divisional_agent,    _make_input("divisional", varga_data)),
            ("yoga",          self._yoga_agent,          _make_input("yoga", yoga_data)),
            ("special_lagna", self._special_lagna_agent, _make_input("special_lagna", special_data)),
            ("jaimini",       self._jaimini_agent,       _make_input("jaimini", jaimini_data)),
        ]

        results = await asyncio.gather(
            *[agent.run(inp) for _, agent, inp in agents_and_inputs]
        )

        for (step, _, _), out in zip(agents_and_inputs, results):
            state.agent_outputs[step] = out.narrative

        state.mark_done("solve")

    # ── Stage: synthesise ─────────────────────────────────────────────────

    async def stage_synthesise(self, state: PipelineState) -> None:
        """Run the master agent (cross-chart weighted) and the Parashari synthesis in parallel."""
        if state.synthesis_raw:
            return

        from vedic_astro.agents.synthesis_agent import SynthesisAgent, SynthesisInput
        from vedic_astro.agents.master_agent import build_master_input

        score_summary = state.score.summary if state.score else ""
        score_table   = state.score.score_table_md if state.score else ""

        synthesis_inp = SynthesisInput(
            query=state.request.query,
            natal_narrative=state.agent_outputs.get("natal", ""),
            dasha_narrative=state.agent_outputs.get("dasha", ""),
            transit_narrative=state.agent_outputs.get("transit", ""),
            divisional_narrative=state.agent_outputs.get("divisional", ""),
            retrieved_cases=state.retrieved_cases,
            score_summary=score_summary,
            score_table=score_table,
        )
        master_inp = build_master_input(
            state,
            query=state.request.query,
            domain=state.request.domain,
            weights=state.chart_weights,
        )

        synthesis_out, master_out = await asyncio.gather(
            self._synthesis.run(synthesis_inp),
            self._master_agent.run(master_inp),
        )

        state.master_output = master_out
        # Master agent output leads the final reading; Parashari synthesis follows as detail
        state.synthesis_raw = synthesis_out.narrative
        state.final_reading = (
            f"{master_out.narrative}\n\n"
            f"--- Parashari Analysis ---\n{synthesis_out.narrative}"
        )
        state.mark_done("synthesise")

    # ── Stage: critique + revise ──────────────────────────────────────────

    async def stage_critique_and_revise(self, state: PipelineState) -> None:
        """
        Run the critic ONLY if the synthesis quality signal is uncertain.

        Quality signal = WeightedScorer.final_score:
          ≥ 0.65 → skip critic (confident reading, likely correct)
          < 0.65 → run critic to check for classical rule violations
        """
        if not state.synthesis_raw:
            return

        all_rules = [r for rules in state.retrieved_rules.values() for r in rules]

        # Skip critic if score is high (efficient path)
        if state.score and state.score.final_score >= 0.65:
            logger.debug("Critic skipped (high confidence score %.2f)", state.score.final_score)
            state.mark_done("critique")
            return

        critic_result = await self._critic.evaluate(
            query=state.request.query,
            synthesis=state.synthesis_raw,
            classical_rules=all_rules,
        )
        state.critic_result = critic_result
        state.mark_done("critique")

        if not critic_result.passed:
            logger.info("Critic FAIL (%.2f) — revising", critic_result.composite_score)
            revised = await self._reviser.revise(
                original=state.synthesis_raw,
                critic_result=critic_result,
                query=state.request.query,
                classical_rules=all_rules,
            )
            state.final_reading = revised
            state.mark_done("revise")

    # ── Stage: format ─────────────────────────────────────────────────────

    def stage_format(self, state: PipelineState) -> StructuredReading:
        critic_notes = []
        was_revised = False
        if state.critic_result:
            critic_notes = state.critic_result.issues
            was_revised = not state.critic_result.passed

        if state.score is None:
            from vedic_astro.learning.scorer import ScoreBreakdown
            state.score = ScoreBreakdown(
                domain="general",
                natal_strength=0.5, dasha_activation=0.5,
                transit_trigger=0.5, yoga_support=0.5,
                dosha_penalty=0.0, final_score=0.5,
                interpretation="moderate_positive",
            )

        reading = self._formatter.format(
            chart_id=state.chart_id,
            query=state.request.query,
            domain=state.request.domain,
            agent_outputs=state.agent_outputs,
            synthesis=state.synthesis_raw,
            final_reading=state.final_reading,
            score=state.score,
            retrieved_rules=state.retrieved_rules,
            retrieved_cases=state.retrieved_cases,
            critic_notes=critic_notes,
            was_revised=was_revised,
        )
        state.mark_done("format")
        return reading

    # ── Serialisation helpers ─────────────────────────────────────────────

    @staticmethod
    def _serialise_chart(chart) -> dict:
        if chart is None:
            return {}
        from vedic_astro.engines.natal_engine import RASHI_NAMES
        return {
            "lagna": f"{RASHI_NAMES[chart.lagna_sign - 1]} (sign {chart.lagna_sign})",
            "planets": {
                p.value: {
                    "sign":  RASHI_NAMES[pos.sign_number - 1],
                    "house": pos.house,
                    "dignity": pos.dignity.value,
                    "retrograde": pos.is_retrograde,
                    "longitude": round(pos.longitude, 2),
                }
                for p, pos in chart.planets.items()
            },
        }

    @staticmethod
    def _serialise_dasha(window, features=None) -> dict:
        if window is None:
            return {}
        maha = window.mahadasha
        antar = window.antardasha
        result = {
            "maha_lord":  maha.lord.value,
            "maha_start": str(maha.start),
            "maha_end":   str(maha.end),
            "maha_elapsed_pct": round(maha.elapsed_fraction(window.query_date) * 100, 1),
            "antar_lord": antar.lord.value if antar else None,
            "antar_start": str(antar.start) if antar else None,
            "antar_end":   str(antar.end)   if antar else None,
            "antar_elapsed_pct": round(antar.elapsed_fraction(window.query_date) * 100, 1) if antar else None,
        }
        # Add interdependence data from features if available
        if features:
            result["maha_lord_d9_dignity"]   = getattr(features, "maha_lord_d9_dignity", "neutral")
            result["maha_lord_d10_dignity"]  = getattr(features, "maha_lord_d10_dignity", "neutral")
            result["dasha_activates_yogas"]  = getattr(features, "dasha_activates_yogas", [])
            result["antar_activates_yogas"]  = getattr(features, "antar_activates_yogas", [])
        return result

    @staticmethod
    def _serialise_transit(overlay, features=None) -> dict:
        if overlay is None:
            return {}
        from vedic_astro.engines.natal_engine import RASHI_NAMES
        result = {
            "sadesati_active": overlay.sadesati_active,
            "sadesati_phase":  overlay.sadesati_phase,
            "gochara": {},
        }
        for planet, g in overlay.gochara.items():
            result["gochara"][planet.value] = {
                "house_from_moon": g.house_from_moon,
                "composite_strength": round(g.composite_strength, 2),
                "favorable": g.is_favorable,
            }
        # Add interdependence data from features if available
        if features:
            result["transit_conjunct_dasha_lord"] = getattr(features, "transit_conjunct_dasha_lord", False)
            result["transit_conjunct_planet"]     = getattr(features, "transit_conjunct_dasha_lord_planet", "")
            result["transit_activates_yogas"]     = getattr(features, "transit_activates_yogas", [])
        return result

    @staticmethod
    def _serialise_vargas(varga_charts: dict) -> dict:
        if not varga_charts:
            return {}
        from vedic_astro.engines.natal_engine import RASHI_NAMES
        out = {}
        for div, vc in varga_charts.items():
            out[f"D{div}"] = {
                "lagna": RASHI_NAMES[vc.lagna_sign - 1],
                "planets": {
                    p.value: RASHI_NAMES[pos.sign_number - 1]
                    for p, pos in vc.planets.items()
                },
            }
        return out

    @staticmethod
    def _serialise_special_lagnas(bundle) -> dict:
        if bundle is None:
            return {}
        from vedic_astro.engines.natal_engine import RASHI_NAMES
        out: dict = {
            "chandra_lagna": RASHI_NAMES[bundle.chandra_lagna - 1],
            "surya_lagna":   RASHI_NAMES[bundle.surya_lagna - 1],
            "special_lagnas": {},
            "arudha_padas":  {},
        }
        for name, sl in bundle.special.items():
            out["special_lagnas"][name] = {
                "sign": sl.sign_name,
                "lord": sl.lord.value,
            }
        for key, pada in bundle.arudhas.padas.items():
            out["arudha_padas"][key] = {
                "sign": pada.sign_name,
                "lord": pada.lord.value,
            }
        return out

    @staticmethod
    def _serialise_jaimini(bundle) -> dict:
        if bundle is None:
            return {}
        from vedic_astro.engines.natal_engine import RASHI_NAMES
        k = bundle.karakas
        active = bundle.active_chara_dasha
        out: dict = {
            "karakas": {
                "atmakaraka":    k.atmakaraka.value,
                "amatyakaraka":  k.amatyakaraka.value,
                "darakaraka":    k.darakaraka.value,
                "putrakaraka":   k.putrakaraka.value,
                "gnatikaraka":   k.gnatikaraka.value,
                "bhratrikaraka": k.bhratrikaraka.value,
                "matrikaraka":   k.matrikaraka.value,
            },
            "karaka_signs": k.sign_numbers,
            "karakamsha": RASHI_NAMES[bundle.karakamsha_sign - 1],
            "active_chara_dasha": {
                "sign": active.sign_name,
                "lord": active.lord.value,
                "start": str(active.start),
                "end":   str(active.end),
                "duration_years": active.duration_years,
            } if active else None,
            "lagna_argala": {
                "argalas": bundle.argalas.get("lagna", {}).argalas if "lagna" in bundle.argalas else [],
                "counter_argalas": bundle.argalas.get("lagna", {}).counter_argalas if "lagna" in bundle.argalas else [],
                "net_strength": bundle.argalas["lagna"].net_argala_strength if "lagna" in bundle.argalas else 0.5,
            },
        }
        return out

    @staticmethod
    def _serialise_yogas(bundle, score, features=None) -> dict:
        out: dict = {"yogas": [], "doshas": [], "score_notes": []}
        if bundle:
            out["yogas"] = [
                {
                    "name": y.name,
                    "strength": y.strength,
                    "forming_planets": [p.value for p in y.contributing_planets],
                    "key_houses": list(y.key_houses),
                }
                for y in bundle.active_yogas
            ]
            out["doshas"] = [{"name": d.name, "severity": d.severity} for d in bundle.active_doshas]
        if score:
            out["score_notes"] = score.notes
        # Add activation state from features
        if features:
            out["dasha_activates"] = getattr(features, "dasha_activates_yogas", [])
            out["transit_activates"] = getattr(features, "transit_activates_yogas", [])
        return out

