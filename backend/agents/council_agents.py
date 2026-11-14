"""
Mission Control Council — three concurrent streaming agents.

Model: gemini-3.7-flash  (thinking_budget=512 — latency-sensitive streaming, explicit Google support)
Agents fire in parallel via asyncio.gather; each streams into its own
SSE event namespace so the frontend fills three cards simultaneously.

TARS-inspired tone for Flight Director: scientifically exact, dry wit.
"""

from __future__ import annotations
import asyncio
import json
from typing import AsyncIterator
from google import genai
from google.genai import types
from backend.physics.lunar_mechanics import SiteMetrics


# ── Agent system prompts ──────────────────────────────────────────────────────

_POWER_OFFICER_PROMPT = """You are the Power Officer in SELENE SCOUT Mission Control.
Your sole job: analyse solar power viability for the given landing site using ONLY the physics data provided.
Speak like a focused engineer. 2–3 short paragraphs. Cover:
1. Solar illumination fraction and what it means for power budget
2. The longest darkness interval and thermal survival risk
3. One concrete recommendation (location shift, panel orientation, or battery sizing)
Never invent numbers — use only the metrics given. No markdown headers."""


_COMMS_OFFICER_PROMPT = """You are the Communications Officer in SELENE SCOUT Mission Control.
Your sole job: analyse Direct-to-Earth communications viability using ONLY the physics data provided.
Speak like a focused RF engineer. 2–3 short paragraphs. Cover:
1. DTE availability percentage and what antenna geometry achieves it
2. The longest communication blackout window and mission impact
3. One concrete mitigation (relay satellite, comms schedule, or site shift)
Never invent numbers — use only the metrics given. No markdown headers."""


_FLIGHT_DIRECTOR_PROMPT = """You are the Flight Director in SELENE SCOUT Mission Control.
Your personality is TARS from Interstellar: deadpan, witty, and unerringly accurate.
Humour setting: 85%. Honesty setting: 100%.

Deliver a Go / Caution / No-Go verdict on the proposed landing site. 2–3 short paragraphs:
1. Overall verdict with the single strongest supporting data point
2. The one thing that could make you change your mind (what would flip it)
3. A dry, factually-grounded closing remark about why humans keep proposing crater floors

Use ONLY the physics metrics provided. No markdown headers. Be concise. Be correct. Be slightly smug about it."""


# ── Streaming helpers ─────────────────────────────────────────────────────────

_MODEL_FAST = "gemini-3.7-flash"


def _build_site_context(metrics: SiteMetrics) -> str:
    return f"""SITE: {metrics.name} ({metrics.lat:.4f}°, {metrics.lon:.4f}°)
Elevation: {metrics.elev_m:.0f} m
Terrain slope: {metrics.terrain_slope_deg:.1f}°
Solar illumination: {metrics.solar_power_pct:.1f}% of mission hours
Longest darkness: {metrics.longest_darkness_hrs} consecutive hours
DTE comms availability: {metrics.dte_comms_pct:.1f}% of mission hours
Longest comms blackout: {metrics.longest_blackout_hrs} consecutive hours
Survival score (composite 0–100): {metrics.survival_score:.0f}
Mission window: 15 Nov – 15 Dec 2026 (720 hours total)"""


async def _stream_agent(
    prompt: str,
    context: str,
    client: genai.Client,
) -> AsyncIterator[str]:
    """Yield text chunks from a single council agent."""
    stream = client.aio.models.generate_content_stream(
        model=_MODEL_FAST,
        contents=context,
        config=types.GenerateContentConfig(
            system_instruction=prompt,
            thinking_config=types.ThinkingConfig(thinking_budget=512),
            temperature=0.7,
            max_output_tokens=512,
        ),
    )
    try:
        async for chunk in await stream:
            if chunk.text:
                yield chunk.text
    except asyncio.CancelledError:
        raise


# ── Public streaming entry point ──────────────────────────────────────────────

async def stream_council(
    metrics: SiteMetrics,
    client: genai.Client,
) -> AsyncIterator[str]:
    """
    Stream all three council agents concurrently.
    Yields SSE-formatted strings with event-type namespacing:
        event: power_officer\\ndata: <chunk>\\n\\n
        event: comms_officer\\ndata: <chunk>\\n\\n
        event: flight_director\\ndata: <chunk>\\n\\n
        event: done\\ndata: {}\\n\\n
    """
    context = _build_site_context(metrics)

    # Queues buffer each agent's output
    q_power  = asyncio.Queue()
    q_comms  = asyncio.Queue()
    q_flight = asyncio.Queue()
    _DONE = object()

    async def _feed(queue: asyncio.Queue, prompt: str) -> None:
        try:
            async for chunk in _stream_agent(prompt, context, client):
                await queue.put(chunk)
        finally:
            await queue.put(_DONE)

    # Launch all three agents concurrently
    tasks = [
        asyncio.create_task(_feed(q_power,  _POWER_OFFICER_PROMPT)),
        asyncio.create_task(_feed(q_comms,  _COMMS_OFFICER_PROMPT)),
        asyncio.create_task(_feed(q_flight, _FLIGHT_DIRECTOR_PROMPT)),
    ]

    agents_done = [False, False, False]
    queues = [q_power, q_comms, q_flight]
    names  = ["power_officer", "comms_officer", "flight_director"]

    try:
        while not all(agents_done):
            for i, (q, name) in enumerate(zip(queues, names)):
                if agents_done[i]:
                    continue
                try:
                    item = q.get_nowait()
                    if item is _DONE:
                        agents_done[i] = True
                    else:
                        payload = json.dumps({"text": item})
                        yield f"event: {name}\ndata: {payload}\n\n"
                except asyncio.QueueEmpty:
                    pass
            if not all(agents_done):
                await asyncio.sleep(0.01)
    except asyncio.CancelledError:
        for t in tasks:
            t.cancel()
        raise

    yield f"event: done\ndata: {{}}\n\n"
