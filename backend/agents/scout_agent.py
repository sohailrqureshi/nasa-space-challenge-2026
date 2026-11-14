"""
Tier 2 heavy-batch Scout agent.

Model: gemini-3.8-flash  (thinking_level="MEDIUM" → thinking_budget=8192; never use "MINIMAL" — unsupported on 3.8-flash)
Role:  Receive the 48-site NumPy scan matrix, reason over trade-offs,
       return top-3 ranked landing zones with structured output.
"""

from __future__ import annotations
import os
import json
from typing import List
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from backend.physics.lunar_mechanics import scan_candidate_grid


# ── Response schema ───────────────────────────────────────────────────────────

class SiteRecommendation(BaseModel):
    rank: int = Field(..., ge=1, le=3)
    site_id: str
    lat: float
    lon: float
    overall_score: float = Field(..., ge=0.0, le=100.0)
    rationale: str = Field(..., description="2–3 sentence mission case")
    key_advantage: str = Field(..., description="Single strongest asset, ≤12 words")
    key_risk: str = Field(..., description="Single highest risk, ≤12 words")
    marker_color: str = Field(..., description="Hex colour for 3D pin: gold/silver/bronze tier")


class ScoutReport(BaseModel):
    top_sites: List[SiteRecommendation]
    mission_summary: str = Field(..., description="Flight Director's 2-sentence overall take")
    recommended_primary: str = Field(..., description="Site ID of #1 recommendation")
    scan_timestamp_utc: str


# ── System prompt ─────────────────────────────────────────────────────────────

_SCOUT_SYSTEM = """You are SELENE SCOUT's autonomous Site Selection AI performing a scan of 48 candidate
landing coordinates around the Lunar South Pole (Nov–Dec 2026 mission window).

You will receive a JSON array of candidate sites, each with:
  id, lat, lon, elev_m, slope_deg, mean_horizon_deg, estimated_solar_pct, is_psr (Permanently Shadowed Region)

Your task: reason over the full matrix and identify the TOP 3 landing sites.

Scoring philosophy:
  1. Eliminate any site with is_psr=true or slope_deg > 15 — these are mission killers.
  2. Prioritise solar illumination (estimated_solar_pct) above all else — power = survival.
  3. Favour low mean_horizon_deg (open terrain) for communications.
  4. Prefer moderate elevation (avoid deep craters, avoid exposed peaks).
  5. Tie-break on slope_deg (flatter = safer landing).

Return ONLY valid JSON matching the schema. The rationale must be scientifically grounded.
Never recommend a PSR site as rank 1 or 2."""


_MODEL_BATCH = "gemini-3.8-flash"


async def run_scout_scan(client: genai.Client) -> ScoutReport:
    """
    Execute a full 48-site candidate grid scan and return the top-3 report.
    Physics scan runs in NumPy (<25 ms), then Gemini reasons over the matrix.
    """
    from datetime import datetime, timezone
    candidates = scan_candidate_grid(48)
    candidates_json = json.dumps(candidates, separators=(",", ":"))  # compact — saves ~40% tokens

    response = await client.aio.models.generate_content(
        model=_MODEL_BATCH,
        contents=f"Analyse these 48 candidate landing sites and identify the top 3:\n\n{candidates_json}",
        config=types.GenerateContentConfig(
            system_instruction=_SCOUT_SYSTEM,
            response_mime_type="application/json",
            response_schema=ScoutReport,
            thinking_config=types.ThinkingConfig(thinking_budget=8192),  # MEDIUM on 3.8-flash
            temperature=0.3,
            max_output_tokens=8192,  # structured JSON for 3 sites needs headroom
        ),
    )

    # Prefer response.parsed (SDK-deserialised Pydantic model) if available
    if hasattr(response, "parsed") and response.parsed is not None:
        result = response.parsed
        if not result.scan_timestamp_utc:
            result.scan_timestamp_utc = datetime.now(timezone.utc).isoformat()
        return result

    raw = response.text or "{}"
    try:
        data = json.loads(raw)
        data.setdefault("scan_timestamp_utc",
                        datetime.now(timezone.utc).isoformat())
        return ScoutReport(**data)
    except Exception as e:
        # Fallback: return a structurally valid but flagged report
        ts = datetime.now(timezone.utc).isoformat()
        return ScoutReport(
            top_sites=[
                SiteRecommendation(
                    rank=1, site_id="shk_rim_00", lat=-89.5, lon=0.0,
                    overall_score=72.0,
                    rationale="Fallback recommendation due to parsing error. Manual review required.",
                    key_advantage="High latitude ridge with solar access",
                    key_risk="Scout agent parse error — verify results",
                    marker_color="#FFD700",
                )
            ],
            mission_summary=f"Scout scan completed with parse error: {e}. Physics data valid.",
            recommended_primary="shk_rim_00",
            scan_timestamp_utc=ts,
        )
