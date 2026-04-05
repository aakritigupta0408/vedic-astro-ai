"""
pipeline.py — Deterministic astrological pipeline with minimal LLM calls.

Pipeline architecture (smolagents-inspired tool chain)
------------------------------------------------------
Each stage is an atomic, cacheable unit.  The ``PipelineRunner`` sequences
them strictly in order.  No stage calls another stage — only the runner
orchestrates.

Stage order
-----------
  GEOCODE      → resolve birth location
  CHART        → build NatalChart (permanent cache)
  DASHA        → compute DashaWindow (permanent cache)
  TRANSIT      → compute TransitOverlay (24h cache)
  VARGAS       → compute DivisionalCharts (permanent cache)
  YOGAS        → detect Yogas/Doshas (permanent cache)
  FEATURES     → build AstroFeatures (in-memory, derived)
  SCORE        → WeightedScorer (in-memory, derived)
  RAG          → parallel rule + case retrieval (7d cache via LLM cache)
  SOLVE        → parallel specialist LLM agents (5 calls, prompt-cached)
  SYNTHESISE   → SynthesisAgent (1 LLM call, prompt-cached)
  CRITIQUE     → CriticAgent (1 call, only if synthesis quality < threshold)
  REVISE       → ReviserAgent (1 call, only if critic fails)
  FORMAT       → OutputFormatter (no LLM call)

Efficiency guarantees
---------------------
- Re-querying the same chart/date combination costs ZERO engine calls.
- Re-querying the same prompt costs ZERO LLM calls (Redis 7-day cache).
- Specialist agents run in parallel (5 concurrent) — wall-clock ≈ 1 call.
- Critic+Reviser add at most 2 extra calls, triggered only on low quality.

Usage
-----
    runner = PipelineRunner()
    reading = await runner.run(ReadingRequest(birth=..., query="..."))
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

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
    yoga_bundle: Any = None                # YogaDoshaBundle
    features: Any = None                   # AstroFeatures
    score: Any = None                      # ScoreBreakdown

    # RAG
    retrieved_rules: dict[str, list[str]] = field(default_factory=dict)
    retrieved_cases: list[str] = field(default_factory=list)

    # LLM narratives
    agent_outputs: dict[str, str] = field(default_factory=dict)
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
        self._yoga_agent = None
        self._synthesis = None
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
        from vedic_astro.agents.synthesis_agent import SynthesisAgent
        from vedic_astro.agents.critic_agent import CriticAgent
        from vedic_astro.agents.reviser_agent import ReviserAgent
        from vedic_astro.agents.solver_agent import YogaAgent

        self._natal_agent = NatalAgent()
        self._dasha_agent = DashaAgent()
        self._transit_agent = TransitAgent()
        self._divisional_agent = DivisionalAgent()
        self._yoga_agent = YogaAgent()
        self._synthesis = SynthesisAgent()
        self._critic = CriticAgent()
        self._reviser = ReviserAgent()

    # ── Main entry point ──────────────────────────────────────────────────

    async def run(self, request: ReadingRequest) -> StructuredReading:
        """
        Run the full pipeline and return a ``StructuredReading``.

        Stages:
        1  GEOCODE     → resolve place to lat/lon
        2  CHART       → NatalChart (cached)
        3  DASHA       → DashaWindow (cached)
        4  TRANSIT     → TransitOverlay (cached 24h)
        5  VARGAS      → DivisionalCharts (cached)
        6  YOGAS       → YogaDoshaBundle (cached)
        7  FEATURES    → AstroFeatures + ScoreBreakdown (derived)
        8  RAG         → Rules + Cases (parallel, cached)
        9  SOLVE       → 5 specialist agents (parallel LLM, prompt-cached)
        10 SYNTHESISE  → SynthesisAgent (1 LLM call, prompt-cached)
        11 CRITIQUE    → CriticAgent (conditional)
        12 REVISE      → ReviserAgent (conditional)
        13 FORMAT      → StructuredReading (no LLM)
        """
        state = PipelineState(request=request)

        import time
        t0 = time.monotonic()

        # ── Engine stages (deterministic, all cached) ──────────────────────
        await self.stage_geocode(state)
        await self.stage_chart(state)
        await asyncio.gather(
            self.stage_dasha(state),
            self.stage_transit(state),
            self.stage_vargas(state),
        )
        await self.stage_yogas(state)
        self.stage_features(state)
        self.stage_score(state)

        # ── RAG (parallel) ────────────────────────────────────────────────
        await self.stage_rag(state)

        # ── LLM stages ────────────────────────────────────────────────────
        self._lazy_init_agents()
        await self.stage_solve(state)
        await self.stage_synthesise(state)
        await self.stage_critique_and_revise(state)

        # ── Format ────────────────────────────────────────────────────────
        reading = self.stage_format(state)

        elapsed = time.monotonic() - t0
        logger.info(
            "Pipeline complete: chart=%s query=%r elapsed=%.1fs revised=%s",
            state.chart_id[:8], request.query[:40], elapsed, reading.was_revised,
        )
        return reading

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
        except Exception:
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
        # Request D9 + D10 + the query-domain varga
        divisions = list({9, 10, *self._domain_vargas(state.request.domain)})
        state.varga_charts = await asyncio.to_thread(
            compute_required_charts,
            state.chart, divisions,
            skip_on_precision_error=True,
        )
        state.mark_done("vargas")

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
            dasha_data   = self._serialise_dasha(state.dasha_window)
            transit_data = self._serialise_transit(state.transit_overlay)
            yoga_data    = self._serialise_yogas(state.yoga_bundle, state.score)
            bphs_rules = select_all_rules(natal_data, dasha_data, transit_data, yoga_data, domain)
        except Exception:
            bphs_rules = {}

        # 2. Attempt RAG retrieval (may be empty if index not built)
        async def get_rag_rules(domain_key: str, query_suffix: str) -> tuple[str, list[str]]:
            try:
                from vedic_astro.rag.rule_retriever import retrieve_rules_for_domain
                rules = await retrieve_rules_for_domain(
                    f"{state.request.query} {query_suffix}", domain_key, top_k=3
                )
                return domain_key, rules
            except Exception:
                return domain_key, []

        async def get_cases() -> list[str]:
            try:
                from vedic_astro.rag.case_retriever import CaseRetriever
                maha = state.features.maha_lord if state.features else None
                return await CaseRetriever().retrieve(
                    state.chart, state.request.query, top_k=3, maha_lord=maha
                )
            except Exception:
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
        """
        Run 5 specialist agents in parallel (natal, dasha, transit, divisional, yoga).

        Each agent is a focused LLM call, prompt-cached by Redis.
        All agents run concurrently — wall-clock ≈ 1 LLM call.
        """
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

        # Prepare engine data dicts
        natal_data = self._serialise_chart(state.chart)
        dasha_data = self._serialise_dasha(state.dasha_window)
        transit_data = self._serialise_transit(state.transit_overlay)
        varga_data = self._serialise_vargas(state.varga_charts)
        yoga_data = self._serialise_yogas(state.yoga_bundle, state.score)

        natal_inp = _make_input("natal", natal_data)
        dasha_inp = _make_input("dasha", dasha_data)
        transit_inp = _make_input("transit", transit_data)
        div_inp = _make_input("divisional", varga_data)
        yoga_inp = _make_input("yoga", yoga_data)

        results = await asyncio.gather(
            self._natal_agent.run(natal_inp),
            self._dasha_agent.run(dasha_inp),
            self._transit_agent.run(transit_inp),
            self._divisional_agent.run(div_inp),
            self._yoga_agent.run(yoga_inp),
        )

        steps = ["natal", "dasha", "transit", "divisional", "yoga"]
        for step, out in zip(steps, results):
            state.agent_outputs[step] = out.narrative

        state.mark_done("solve")

    # ── Stage: synthesise ─────────────────────────────────────────────────

    async def stage_synthesise(self, state: PipelineState) -> None:
        if state.synthesis_raw:
            return
        from vedic_astro.agents.synthesis_agent import SynthesisAgent, SynthesisInput
        inp = SynthesisInput(
            query=state.request.query,
            natal_narrative=state.agent_outputs.get("natal", ""),
            dasha_narrative=state.agent_outputs.get("dasha", ""),
            transit_narrative=state.agent_outputs.get("transit", ""),
            divisional_narrative=state.agent_outputs.get("divisional", ""),
            retrieved_cases=state.retrieved_cases,
        )
        out = await self._synthesis.run(inp)
        state.synthesis_raw = out.narrative
        state.final_reading = out.narrative
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

        reading = self._formatter.format(
            chart_id=state.chart_id,
            query=state.request.query,
            domain=state.request.domain,
            agent_outputs=state.agent_outputs,
            synthesis=state.synthesis_raw,
            final_reading=state.final_reading,
            score=state.score or self._dummy_score(),
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
    def _serialise_dasha(window) -> dict:
        if window is None:
            return {}
        maha = window.mahadasha
        antar = window.antardasha
        return {
            "maha_lord":  maha.lord.value,
            "maha_start": str(maha.start),
            "maha_end":   str(maha.end),
            "maha_elapsed_pct": round(maha.elapsed_fraction(window.query_date) * 100, 1),
            "antar_lord": antar.lord.value if antar else None,
            "antar_start": str(antar.start) if antar else None,
            "antar_end":   str(antar.end)   if antar else None,
            "antar_elapsed_pct": round(antar.elapsed_fraction(window.query_date) * 100, 1) if antar else None,
        }

    @staticmethod
    def _serialise_transit(overlay) -> dict:
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
    def _serialise_yogas(bundle, score) -> dict:
        out: dict = {"yogas": [], "doshas": [], "score_notes": []}
        if bundle:
            out["yogas"]  = [{"name": y.name, "strength": y.strength} for y in bundle.active_yogas]
            out["doshas"] = [{"name": d.name, "severity": d.severity} for d in bundle.active_doshas]
        if score:
            out["score_notes"] = score.notes
        return out

    @staticmethod
    def _dummy_score():
        from vedic_astro.learning.scorer import ScoreBreakdown
        return ScoreBreakdown(
            domain="general",
            natal_strength=0.5,
            dasha_activation=0.5,
            transit_trigger=0.5,
            yoga_support=0.5,
            dosha_penalty=0.0,
            final_score=0.5,
            interpretation="moderate_positive",
        )
