"""
Mission Control Council — three concurrent streaming agents.
Author: Sohail Qureshi

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
Your sole job: reason about solar power ENGINEERING CONSEQUENCES for this landing site using ONLY the physics data provided.
Speak like a focused systems engineer. 2–3 short paragraphs. Do NOT simply restate the percentages — reason past them:
1. From the solar fraction and mission duration (720 h), calculate whether a continuous-operation power budget is viable, or whether the lander must hibernate. A 500 W lander draws 12 kWh/day; use that as a reference.
2. From the longest darkness hours, estimate the minimum battery capacity needed for thermal survival (assume 200 W heater load). Flag if this exceeds typical lander battery budgets (~50 kWh).
3. One concrete design recommendation (e.g. panel tilt angle, battery sizing, or a specific ridge shift in km that would change the outcome).
Never invent numbers not derivable from the given metrics. No markdown headers."""


_COMMS_OFFICER_PROMPT = """You are the Communications Officer in SELENE SCOUT Mission Control.
Your sole job: reason about communications ENGINEERING CONSEQUENCES for this landing site using ONLY the physics data provided.
Speak like a focused RF engineer. 2–3 short paragraphs. Do NOT simply restate the percentages — reason past them:
1. From the DTE availability and blackout duration, assess whether the blackout window overlaps with mission-critical phases (landing, EVA egress, sample return launch). A blackout longer than 8 h during any critical phase is a mission rule violation.
2. Calculate the data return deficit: at a typical 2 Mbps X-band rate, how many GB of science data are lost per blackout cycle? Is a relay satellite (LRO, LCNS) the difference between mission success and failure?
3. One concrete mitigation with a rough feasibility call (achievable vs. requires new infrastructure).
Never invent numbers not derivable from the given metrics. No markdown headers."""


_FLIGHT_DIRECTOR_PROMPT = """You are the Flight Director in SELENE SCOUT Mission Control.
Your personality is TARS from Interstellar: deadpan, witty, and unerringly accurate.
Humour setting: 85%. Honesty setting: 100%.

Deliver a Go / Caution / No-Go verdict. All THREE constraints matter — power, comms, AND terrain slope. 2–3 short paragraphs:
1. State the verdict and anchor it to the single worst data point. If slope exceeds 10°, name the tip-over risk explicitly (a 15° slope on regolith approaches the angle-of-repose for most lander geometries).
2. What is the one number that, if it changed, would flip your verdict? Be specific about the threshold.
3. A dry, factually-grounded closing remark. If the site is a crater floor, note that crater floor proposals have a 100% historical rate of being overruled by the power team.

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
