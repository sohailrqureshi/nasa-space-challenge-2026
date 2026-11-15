"""
SELENE SCOUT — FastAPI application entry point.
Author: Sohail Qureshi

Serves:
  /api/*         — all JSON + SSE endpoints
  /              — React/Vite static bundle (dist/)

Startup pre-scores all 5 Artemis candidate sites so the first
site-select request is instantaneous.
"""

from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()  # loads .env before any os.environ reads below
import asyncio
import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.physics.lunar_mechanics import (
    SiteMetrics, score_site, score_all_candidate_sites,
    CANDIDATE_SITES, scan_candidate_grid,
)
from backend.physics import ephemeris as jpl_eph
from backend.agents.command_agent import build_client, parse_command, ViewerCommand
from backend.agents.council_agents import stream_council
from backend.agents.scout_agent import run_scout_scan

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("selene-scout")

# ── App state ─────────────────────────────────────────────────────────────────

_site_cache: Dict[str, SiteMetrics] = {}
_genai_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _genai_client, _site_cache

    # 1. Fetch real JPL Horizons ephemeris for all 5 candidate sites.
    #    All 10 HTTP requests run concurrently; typical wall-clock: 3–6 s.
    log.info("Loading JPL Horizons ephemeris (Sun + Earth for 5 sites)…")
    jpl_ok = await jpl_eph.load_jpl_ephemeris()
    if jpl_ok:
        log.info("JPL Horizons loaded: %s", jpl_eph.cache_summary())
    else:
        log.warning("JPL Horizons unavailable — falling back to analytical ephemeris")

    # 2. Score candidate sites (uses JPL data if loaded, analytical otherwise)
    log.info("Pre-scoring Artemis candidate sites…")
    loop = asyncio.get_event_loop()
    metrics_list = await loop.run_in_executor(None, score_all_candidate_sites)
    _site_cache = {m.site_id: m for m in metrics_list}
    log.info("Scored %d sites: %s", len(_site_cache), list(_site_cache.keys()))

    _genai_client = build_client()
    log.info("Gemini client initialised")
    yield
    log.info("Shutdown complete")


app = FastAPI(
    title="SELENE SCOUT — Lunar Landing Site Navigator",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "sites_cached": len(_site_cache),
        "jpl_ephemeris": jpl_eph.is_loaded(),
        "jpl_sites": jpl_eph.cache_summary(),
    }


# ── Static candidate site list ────────────────────────────────────────────────

@app.get("/api/sites")
async def get_sites():
    """Return all 5 Artemis candidate sites with pre-computed physics metrics."""
    return [
        {**vars(m), "horizon_profile": m.horizon_profile[:72]}
        for m in _site_cache.values()
    ]


@app.get("/api/sites/{site_id}")
async def get_site(site_id: str):
    if site_id not in _site_cache:
        raise HTTPException(404, f"Unknown site: {site_id}")
    m = _site_cache[site_id]
    return vars(m)


# ── Natural language command parsing ─────────────────────────────────────────

class CommandRequest(BaseModel):
    query: str


@app.post("/api/command")
async def command(req: CommandRequest) -> ViewerCommand:
    """
    Parse a natural-language command into a structured ViewerCommand.
    Tier 1: gemini-2.5-flash-lite, thinking_budget=0.  Target TTFT <500 ms.
    """
    if not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")
    return await parse_command(req.query, _genai_client)


# ── Mission Control Council — SSE streaming ───────────────────────────────────

@app.get("/api/council/stream")
async def council_stream(site_id: str = Query(...)):
    """
    Stream three concurrent council agent responses for the selected site.

    SSE event types:  power_officer | comms_officer | flight_director | done
    Each data payload: {"text": "<chunk>"}

    Three agents fire in parallel (asyncio.gather) so all three cards fill
    simultaneously — no 3× sequential lag.
    """
    if site_id not in _site_cache:
        raise HTTPException(404, f"Unknown site: {site_id}")
    metrics = _site_cache[site_id]

    async def generate():
        try:
            async for sse_line in stream_council(metrics, _genai_client):
                yield sse_line
        except asyncio.CancelledError:
            # Client disconnected — clean exit, no leaked gRPC streams
            return

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Batch zone scanner ────────────────────────────────────────────────────────

@app.post("/api/scan-zones")
async def scan_zones():
    """
    Run 48-point NumPy candidate grid scan then analyse with gemini-2.5-flash.
    Tier 2: thinking_budget=4096.  Expected latency: 2–5 s.
    Returns top-3 ranked landing zones with trade-off rationale.
    """
    report = await run_scout_scan(_genai_client)
    return report.model_dump()


# ── Serve React frontend ──────────────────────────────────────────────────────

_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="static")
else:
    @app.get("/")
    async def root():
        return JSONResponse(
            {"message": "Frontend not built. Run: cd frontend && npm run build"},
            status_code=200,
        )
