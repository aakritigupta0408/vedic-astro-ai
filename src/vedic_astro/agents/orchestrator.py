"""
orchestrator.py — Top-level pipeline orchestrator.

Flow
----
1. Resolve birth location → lat/lon/timezone
2. Compute NatalChart (cached permanently)
3. Fan-out to specialist agents (parallel async):
   - NatalAgent  ← natal engine data + RAG rules
   - DashaAgent  ← dasha engine data + RAG rules
   - TransitAgent ← transit overlay + RAG rules
   - DivisionalAgent ← varga engine data + RAG rules
4. SynthesisAgent ← all narratives + RAG cases
5. CriticAgent evaluates synthesis
6. ReviserAgent (conditional, max 1 pass) if critic fails
7. Persist report to MongoDB
8. Return final reading

The orchestrator is the ONLY place that touches all modules.
Agents only call the LLM; they never call each other.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BirthData:
    """All information needed to build a natal chart."""
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int = 0
    place: str = ""        # free-text place name (geocoded)
    lat: Optional[float] = None   # or supply directly
    lon: Optional[float] = None
    timezone_str: str = "UTC"


@dataclass
class ReadingRequest:
    """Full request to the pipeline."""
    birth: BirthData
    query: str
    query_date: Optional[date] = None   # defaults to today


@dataclass
class ReadingResponse:
    """Final structured response from the pipeline."""
    chart_id: str
    query: str
    reading: str               # final narrative (post-revision if needed)
    critic_score: float
    was_revised: bool
    natal_narrative: str
    dasha_narrative: str
    transit_narrative: str
    divisional_narrative: str


class AstrologyOrchestrator:
    """
    Top-level pipeline coordinator.

    Usage::

        orch = AstrologyOrchestrator()
        response = await orch.run(ReadingRequest(birth=..., query="..."))
        print(response.reading)
    """

    def __init__(self) -> None:
        from vedic_astro.agents.natal_agent import NatalAgent
        from vedic_astro.agents.dasha_agent import DashaAgent
        from vedic_astro.agents.transit_agent import TransitAgent
        from vedic_astro.agents.divisional_agent import DivisionalAgent
        from vedic_astro.agents.synthesis_agent import SynthesisAgent, SynthesisInput
        from vedic_astro.agents.critic_agent import CriticAgent
        from vedic_astro.agents.reviser_agent import ReviserAgent

        self._natal_agent = NatalAgent()
        self._dasha_agent = DashaAgent()
        self._transit_agent = TransitAgent()
        self._divisional_agent = DivisionalAgent()
        self._synthesis = SynthesisAgent()
        self._critic = CriticAgent()
        self._reviser = ReviserAgent()

    async def run(self, request: ReadingRequest) -> ReadingResponse:
        """Execute the full pipeline and return the final reading."""
        from vedic_astro.settings import settings

        query_date = request.query_date or date.today()

        # ── 1. Resolve location ──────────────────────────────────────────────
        birth = await self._resolve_birth(request.birth)

        # ── 2. Compute natal chart ───────────────────────────────────────────
        chart = await self._build_chart(birth)
        chart_id = chart.chart_id
        logger.info("Orchestrator: chart_id=%s query=%r", chart_id, request.query)

        # ── 3. Compute engine outputs ────────────────────────────────────────
        dasha_data, transit_data, varga_data = await asyncio.gather(
            self._compute_dasha(chart, birth, query_date),
            self._compute_transit(chart, query_date),
            self._compute_vargas(chart, birth),
        )

        # ── 4. RAG retrieval (parallel) ──────────────────────────────────────
        natal_rules, dasha_rules, transit_rules, div_rules, cases = await asyncio.gather(
            self._retrieve_rules(f"natal {request.query}"),
            self._retrieve_rules(f"dasha {request.query}"),
            self._retrieve_rules(f"gochara transit {request.query}"),
            self._retrieve_rules(f"varga divisional {request.query}"),
            self._retrieve_cases(chart, request.query),
        )

        # ── 5. Fan-out to specialist agents (parallel) ───────────────────────
        from vedic_astro.agents.base import AgentInput

        natal_out, dasha_out, transit_out, div_out = await asyncio.gather(
            self._natal_agent.run(AgentInput(
                chart_id=chart_id, query=request.query,
                engine_data=chart.model_dump(mode="json"),
                retrieved_rules=natal_rules, retrieved_cases=[],
            )),
            self._dasha_agent.run(AgentInput(
                chart_id=chart_id, query=request.query,
                engine_data=dasha_data,
                retrieved_rules=dasha_rules, retrieved_cases=[],
            )),
            self._transit_agent.run(AgentInput(
                chart_id=chart_id, query=request.query,
                engine_data=transit_data,
                retrieved_rules=transit_rules, retrieved_cases=[],
            )),
            self._divisional_agent.run(AgentInput(
                chart_id=chart_id, query=request.query,
                engine_data=varga_data,
                retrieved_rules=div_rules, retrieved_cases=[],
            )),
        )

        # ── 6. Synthesis ─────────────────────────────────────────────────────
        from vedic_astro.agents.synthesis_agent import SynthesisInput

        synthesis_out = await self._synthesis.run(SynthesisInput(
            query=request.query,
            natal_narrative=natal_out.narrative,
            dasha_narrative=dasha_out.narrative,
            transit_narrative=transit_out.narrative,
            divisional_narrative=div_out.narrative,
            retrieved_cases=cases,
        ))

        # ── 7. Critic ────────────────────────────────────────────────────────
        all_rules = natal_rules + dasha_rules + transit_rules
        critic_result = await self._critic.evaluate(
            query=request.query,
            synthesis=synthesis_out.narrative,
            classical_rules=all_rules,
        )

        # ── 8. Conditional revision ──────────────────────────────────────────
        final_reading = synthesis_out.narrative
        was_revised = False

        if not critic_result.passed:
            logger.info(
                "Critic FAIL (score=%.2f) — triggering reviser",
                critic_result.composite_score,
            )
            final_reading = await self._reviser.revise(
                original=synthesis_out.narrative,
                critic_result=critic_result,
                query=request.query,
                classical_rules=all_rules,
            )
            was_revised = True

        # ── 9. Persist ───────────────────────────────────────────────────────
        await self._persist_report(
            chart_id=chart_id,
            request=request,
            final_reading=final_reading,
            critic_score=critic_result.composite_score,
            was_revised=was_revised,
        )

        return ReadingResponse(
            chart_id=chart_id,
            query=request.query,
            reading=final_reading,
            critic_score=critic_result.composite_score,
            was_revised=was_revised,
            natal_narrative=natal_out.narrative,
            dasha_narrative=dasha_out.narrative,
            transit_narrative=transit_out.narrative,
            divisional_narrative=div_out.narrative,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _resolve_birth(self, birth: BirthData) -> BirthData:
        """Geocode place if lat/lon not supplied."""
        if birth.lat is not None and birth.lon is not None:
            return birth
        if not birth.place:
            raise ValueError("Either lat/lon or place name must be provided.")
        from vedic_astro.tools.geo import get_geo_resolver
        resolver = get_geo_resolver()
        loc = await resolver.resolve(birth.place)
        return BirthData(
            year=birth.year, month=birth.month, day=birth.day,
            hour=birth.hour, minute=birth.minute, second=birth.second,
            place=birth.place, lat=loc.lat, lon=loc.lon,
            timezone_str=loc.timezone,
        )

    async def _build_chart(self, birth: BirthData):
        """Compute or retrieve cached natal chart."""
        import asyncio
        from vedic_astro.tools.datetime_utils import local_to_utc
        from vedic_astro.engines.natal_engine import build_natal_chart

        utc_dt = local_to_utc(
            birth.year, birth.month, birth.day,
            birth.hour, birth.minute, birth.second,
            birth.timezone_str,
        )
        # build_natal_chart is sync + internally cached
        return await asyncio.to_thread(
            build_natal_chart,
            birth.year, birth.month, birth.day,
            birth.hour, birth.minute,
            birth.lat, birth.lon,
        )

    async def _compute_dasha(self, chart, birth: BirthData, query_date: date) -> dict:
        import asyncio
        from vedic_astro.engines.dasha_engine import get_active_dasha_window
        from vedic_astro.engines.natal_engine import PlanetName
        from datetime import datetime

        moon_lon = chart.planets[PlanetName.MOON].longitude
        birth_dt = datetime(
            birth.year, birth.month, birth.day,
            birth.hour, birth.minute, birth.second,
        )
        window = await asyncio.to_thread(
            get_active_dasha_window,
            moon_lon, birth_dt, query_date, chart, depth=2,
        )
        return {
            "maha": window.maha.__dict__,
            "antar": window.antar.__dict__ if window.antar else None,
        }

    async def _compute_transit(self, chart, query_date: date) -> dict:
        import asyncio
        from vedic_astro.engines.transit_engine import (
            compute_transit_snapshot, compute_transit_overlay
        )
        snapshot = await asyncio.to_thread(compute_transit_snapshot, query_date)
        overlay = await asyncio.to_thread(compute_transit_overlay, snapshot, chart)
        return {
            "sade_sati": overlay.sade_sati_active,
            "sade_sati_phase": overlay.sade_sati_phase,
            "gochara": [
                {
                    "planet": g.planet.value,
                    "house_from_moon": g.house_from_moon,
                    "composite_strength": g.composite_strength,
                    "is_favorable": g.is_favorable,
                }
                for g in overlay.gochara_strengths
            ],
        }

    async def _compute_vargas(self, chart, birth: BirthData) -> dict:
        import asyncio
        from vedic_astro.engines.varga_engine import compute_required_charts
        from vedic_astro.engines.natal_engine import PlanetName
        from datetime import datetime

        birth_dt = datetime(
            birth.year, birth.month, birth.day,
            birth.hour, birth.minute, birth.second,
        )
        vargas = await asyncio.to_thread(
            compute_required_charts,
            chart, birth_dt, [9, 10],
            skip_on_precision_error=True,
        )
        return {
            str(div): {
                p.value: pos.sign_number
                for p, pos in vc.planets.items()
            }
            for div, vc in vargas.items()
        }

    async def _retrieve_rules(self, query: str) -> list[str]:
        """Retrieve classical rules from RAG (graceful stub if unavailable)."""
        try:
            from vedic_astro.rag.rule_retriever import RuleRetriever
            retriever = RuleRetriever()
            return await retriever.retrieve(query, top_k=5)
        except Exception as exc:
            logger.debug("Rule retrieval unavailable: %s", exc)
            return []

    async def _retrieve_cases(self, chart, query: str) -> list[str]:
        """Retrieve similar VedAstro cases from RAG."""
        try:
            from vedic_astro.rag.case_retriever import CaseRetriever
            retriever = CaseRetriever()
            return await retriever.retrieve(chart, query, top_k=3)
        except Exception as exc:
            logger.debug("Case retrieval unavailable: %s", exc)
            return []

    async def _persist_report(
        self,
        chart_id: str,
        request: ReadingRequest,
        final_reading: str,
        critic_score: float,
        was_revised: bool,
    ) -> None:
        try:
            from vedic_astro.storage.mongo_client import get_mongo_db
            from vedic_astro.storage.report_repo import ReportRepository
            db = await get_mongo_db()
            repo = ReportRepository(db)
            await repo.save(chart_id, request.query, {
                "reading": final_reading,
                "critic_score": critic_score,
                "was_revised": was_revised,
            })
        except Exception as exc:
            logger.warning("Report persist failed: %s", exc)
