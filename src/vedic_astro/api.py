"""
api.py — FastAPI application.

Endpoints
---------
POST /reading      — Full natal + dasha + transit + divisional reading
GET  /chart/{id}   — Retrieve a saved chart by fingerprint ID
GET  /health       — Liveness check

All endpoints are async.  MongoDB and Redis connections are established
on application startup and reused across requests.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="Vedic Astrology AI",
    description="Production Vedic astrology readings with deterministic computation + LLM synthesis.",
    version="0.1.0",
)


# ─────────────────────────────────────────────────────────────────────────────
# Request / response schemas
# ─────────────────────────────────────────────────────────────────────────────

class BirthDataRequest(BaseModel):
    year: int  = Field(..., ge=1800, le=2100)
    month: int = Field(..., ge=1,    le=12)
    day: int   = Field(..., ge=1,    le=31)
    hour: int  = Field(..., ge=0,    le=23)
    minute: int = Field(..., ge=0,   le=59)
    place: Optional[str] = None
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    timezone_str: str = "UTC"


class ReadingRequest(BaseModel):
    birth: BirthDataRequest
    query: str = Field(..., min_length=5, max_length=500)
    query_date: Optional[date] = None


class ReadingResponseSchema(BaseModel):
    chart_id: str
    query: str
    reading: str
    critic_score: float
    was_revised: bool
    natal_narrative: str
    dasha_narrative: str
    transit_narrative: str
    divisional_narrative: str


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event() -> None:
    """Warm up connections on startup."""
    from vedic_astro.tools.cache import get_cache
    cache = get_cache()
    await cache._ensure_connected()


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/reading", response_model=ReadingResponseSchema)
async def get_reading(req: ReadingRequest) -> ReadingResponseSchema:
    """
    Generate a full Vedic astrology reading.

    Requires either ``place`` (geocoded) or explicit ``lat``/``lon``.
    """
    from vedic_astro.agents.orchestrator import (
        AstrologyOrchestrator, BirthData, ReadingRequest as OrcReq
    )

    birth = BirthData(
        year=req.birth.year,
        month=req.birth.month,
        day=req.birth.day,
        hour=req.birth.hour,
        minute=req.birth.minute,
        place=req.birth.place or "",
        lat=req.birth.lat,
        lon=req.birth.lon,
        timezone_str=req.birth.timezone_str,
    )

    try:
        orch = AstrologyOrchestrator()
        result = await orch.run(OrcReq(birth=birth, query=req.query, query_date=req.query_date))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ReadingResponseSchema(
        chart_id=result.chart_id,
        query=result.query,
        reading=result.reading,
        critic_score=result.critic_score,
        was_revised=result.was_revised,
        natal_narrative=result.natal_narrative,
        dasha_narrative=result.dasha_narrative,
        transit_narrative=result.transit_narrative,
        divisional_narrative=result.divisional_narrative,
    )


@app.get("/chart/{chart_id}")
async def get_chart(chart_id: str) -> dict:
    """Retrieve a saved natal chart document by fingerprint ID."""
    try:
        from vedic_astro.storage.mongo_client import get_mongo_db
        from vedic_astro.storage.chart_repo import ChartRepository
        db = await get_mongo_db()
        repo = ChartRepository(db)
        chart = await repo.find(chart_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {exc}") from exc

    if chart is None:
        raise HTTPException(status_code=404, detail="Chart not found")

    return chart.model_dump(mode="json")
