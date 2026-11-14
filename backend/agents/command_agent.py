"""
Tier 1 real-time command agent.

Model: gemini-2.5-flash-lite  (thinking_budget=0 → lowest latency)
Role:  Parse natural-language user queries into structured viewer commands
       + a concise spoken response. Target TTFT < 500 ms.
"""

from __future__ import annotations
import os
import json
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types


# ── Response schema ───────────────────────────────────────────────────────────

class CoordinatesPayload(BaseModel):
    lat: float
    lon: float
    altitude_m: float = 50000.0


class TimeRangePayload(BaseModel):
    start_iso: str
    end_iso: str
    speed_multiplier: int = 100


class ViewerCommand(BaseModel):
    action: Literal[
        "fly_to", "set_time_range", "compare_sites",
        "play_flythrough_tour", "scan_zones", "none"
    ]
    site_id: Optional[str] = Field(None, description="Target site ID for fly_to/compare")
    coordinates: Optional[CoordinatesPayload] = None
    time_range: Optional[TimeRangePayload] = None
    sites: Optional[List[str]] = Field(None, description="Site IDs for compare_sites")
    response_text: str = Field(..., description="Concise spoken response shown in the HUD")
    response_tone: Literal["informative", "cautionary", "excited", "sardonic"] = "informative"


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are SELENE SCOUT's Mission Control AI, navigating humanity's return to the lunar south pole.

Available landing sites:
- shackleton_rim      Shackleton Crater Rim (-89.68°S, 129.20°E) — high solar, Artemis favourite
- connecting_ridge    Connecting Ridge (-89.45°S, 222.50°E) — moderate solar, good comms
- de_gerlache_rim     de Gerlache Rim (-88.71°S, 291.70°E) — excellent comms, some shadow risk
- malapert_massif     Malapert Massif (-86.00°S, 2.50°E) — near-continuous solar, high altitude
- shackleton_floor    Shackleton Crater Floor (-89.90°S, 0.00°E) — permanently shadowed region

Respond ONLY with valid JSON matching the schema. Keep response_text under 60 words.
When the user asks to "scan", "find best", or "discover optimal" sites → action: scan_zones.
When the user asks to "fly to", "go to", "show me", "navigate to" a site → action: fly_to.
When the user asks to "compare" multiple sites → action: compare_sites.
When the user asks to "play", "tour", or "fly around" → action: play_flythrough_tour.
Otherwise → action: none with an informative response_text."""


# ── Client factory (shared with other agents) ─────────────────────────────────

def build_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    return genai.Client(
        vertexai=True,
        project=os.environ.get("GCP_PROJECT", ""),
        location=os.environ.get("GCP_LOCATION", "global"),
    )


_MODEL_FAST = "gemini-2.5-flash-lite"


async def parse_command(user_input: str, client: genai.Client) -> ViewerCommand:
    """
    Parse a natural-language command into a structured ViewerCommand.
    Uses response_schema for guaranteed-valid JSON output.
    """
    response = await client.aio.models.generate_content(
        model=_MODEL_FAST,
        contents=user_input,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=ViewerCommand,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            temperature=0.2,
            max_output_tokens=512,
        ),
    )
    raw = response.text or "{}"
    try:
        data = json.loads(raw)
        return ViewerCommand(**data)
    except Exception:
        return ViewerCommand(
            action="none",
            response_text="I couldn't parse that command. Try: 'Fly to Shackleton Rim' or 'Scan for best sites'.",
            response_tone="informative",
        )
