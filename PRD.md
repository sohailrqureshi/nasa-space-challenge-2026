# SELENE SCOUT — Product Requirements Document

**Project:** SELENE SCOUT — Lunar Landing Site Navigator
**Author:** Sohail Qureshi
**Challenge:** 2026 NASA International Space Apps Challenge
**Mission window:** 15 Nov – 15 Dec 2026, Lunar South Pole (85–90°S)
**Version:** 1.0.0

---

## 1. Problem Statement

Selecting an Artemis landing site in the lunar south polar region requires reconciling three competing survival constraints simultaneously: solar illumination (power), Earth visibility (communications), and terrain slope (safe landing and traverse). No existing public tool lets a mission planner — or a judge evaluating such a tool — interactively explore those trade-offs in real time against actual physics data for a specific mission window.

---

## 2. Product Vision

A browser-based 3D mission planning tool that combines real ephemeris data, physics-accurate terrain analysis, and a multi-agent AI council to give any user an instant, grounded answer to: *"Where exactly should we land, and why?"*

---

## 3. Users

| User | Need |
|---|---|
| NASA mission planner / judge | Quickly evaluate all candidate sites across power, comms, and terrain in one view |
| Space Apps hackathon evaluator | Understand the technical depth and real-data integration at a glance |
| Space enthusiast / student | Explore the lunar south pole interactively with accurate science |

---

## 4. Artemis Candidate Sites

Five sites sourced from NASA ESMD site selection reports:

| Site | Lat | Lon | Elev (m) | Notes |
|---|---|---|---|---|
| Shackleton Crater Rim | −89.65° | 129.20°E | +1 200 | Artemis favourite; highest rim solar |
| Connecting Ridge | −89.45° | 222.50°E | +800 | Moderate solar; best DTE geometry |
| de Gerlache Rim | −88.71° | 291.70°E | +600 | Excellent comms; some shadow risk |
| Malapert Massif | −86.00° | 2.50°E | +5 500 | Near-continuous solar; highest elevation |
| Shackleton Crater Floor | −89.90° | 0.00°E | −2 800 | Permanently shadowed; mission-critical no-go |

---

## 5. Core Features

### 5.1 Real-Time 3D Globe

- CesiumJS rendering of the Moon with NASA LRO WAC Mosaic imagery (LROC 303 ppd) served from NASA Moon Trek WMTS
- Lunar ellipsoid (`Cesium.Ellipsoid.MOON`) applied globally before any object instantiation
- `preserveDrawingBuffer: true` for pixel-level WebGL access in automated tests
- Base colour `#4a4a4a` as a grey fallback that is never the deep-blue default

### 5.2 Physics Engine

- Synthetic DEM calibrated to NASA LRO LOLA south pole topography (200×200 grid, ~1 km sub-polar resolution)
- Horizon profile computed via ray-marching at 72 azimuth angles per site
- Solar illumination fraction: sun elevation above terrain horizon vs. 720-hour mission window (1 h steps)
- DTE availability: Earth elevation above 3° clearance angle
- Terrain slope computed via central-difference from DEM
- **Primary ephemeris:** JPL Horizons API (live HTTP pre-fetch at startup for all 5 sites, concurrent)
- **Fallback ephemeris:** USNO simplified solar coordinates + two-term libration model

Scoring formula:
```
score = 0.5 × solar_pct + 0.3 × dte_pct + 0.2 × (1 − slope/15)
        − 25 × is_psr
        − max(0, (slope − 15) × 5)
```

### 5.3 Mission Control Council (AI)

Three Gemini-powered agents stream their analysis in parallel (no sequential lag):

| Agent | Model | Role |
|---|---|---|
| Power Officer | gemini-2.5-flash | Solar power viability — illumination fraction, thermal risk, battery sizing |
| Comms Officer | gemini-2.5-flash | DTE communications — blackout windows, relay mitigation |
| Flight Director | gemini-2.5-flash | Go/Caution/No-Go verdict, TARS-inspired dry wit, humour 85% |

All three agents receive only the physics-computed metrics (no hallucinated numbers).

### 5.4 Natural Language Command Bar

- Model: gemini-2.5-flash-lite, `thinking_budget=0`
- Target TTFT: < 500 ms
- Supported actions: `fly_to`, `set_time_range`, `compare_sites`, `play_flythrough_tour`, `scan_zones`, `none`
- Parses free-form English into a structured `ViewerCommand` returned as JSON

### 5.5 Autonomous Zone Scanner

- Model: gemini-2.5-flash, `thinking_level="MEDIUM"` (thinking_budget = 8 192 tokens)
- Scans a 48-point NumPy candidate grid across 85–90°S
- Eliminates PSR sites and slopes > 15° before ranking
- Returns top-3 sites with rationale, key advantage, key risk, and hex marker colour
- Triggered by "Scan Shackleton Rim" demo or `scan_zones` command

### 5.6 Timeline Scrubber

- 30-day mission window playback (15 Nov – 15 Dec 2026)
- Speed controls: 1×, 100×, 1 000×
- Timeline bar shows mission window boundaries
- Site illumination and DTE status update as time progresses

---

## 6. Architecture

```
┌─────────────────────────────────────────────────────┐
│  Browser (React + CesiumJS + Zustand)               │
│  CesiumViewer · MissionControlHUD · CouncilFeed     │
│  TimelineScrubber · MissionBriefingOverlay          │
└───────────────────┬─────────────────────────────────┘
                    │ HTTP / SSE
┌───────────────────▼─────────────────────────────────┐
│  FastAPI (Python 3.11+)                             │
│  /api/health · /api/sites · /api/command            │
│  /api/council/stream (SSE) · /api/scan-zones        │
└──────┬──────────────────────────┬───────────────────┘
       │                          │
┌──────▼──────┐          ┌────────▼────────┐
│ Physics     │          │ Gemini API      │
│ NumPy DEM   │          │ Flash-lite ×1   │
│ JPL Horizons│          │ Flash ×3 SSE    │
│ Lunar mech. │          │ Flash scout ×1  │
└─────────────┘          └─────────────────┘
```

**Key design decisions:**

- Physics is deterministic NumPy — no LLM touches the numbers
- AI agents receive only pre-computed physics context — no hallucinated coordinates
- JPL Horizons pre-fetched at startup (concurrent HTTP) so first site selection is instant
- Council agents fire in parallel (`asyncio.gather`) — all three cards fill simultaneously

---

## 7. API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Server status, JPL ephemeris state, cached site count |
| GET | `/api/sites` | All 5 candidate sites with pre-computed physics metrics |
| GET | `/api/sites/{site_id}` | Full metrics for a single site |
| POST | `/api/command` | Natural language → `ViewerCommand` JSON |
| GET | `/api/council/stream?site_id=` | SSE stream of three council agents |
| POST | `/api/scan-zones` | 48-point grid scan → top-3 ranked zones |

---

## 8. Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, CesiumJS 1.x, Zustand, Vite 6 |
| Backend | Python 3.11+, FastAPI, Uvicorn, NumPy, httpx |
| AI | Google Gemini API (google-genai SDK) |
| Imagery | NASA Moon Trek WMTS (LRO WAC Mosaic 303 ppd) |
| Ephemeris | JPL Horizons API + USNO analytical fallback |
| Testing | pytest 8, Playwright, httpx |

---

## 9. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Command TTFT | < 500 ms (Tier 1 flash-lite) |
| Council first-token latency | < 2 s per agent (parallel streaming) |
| Zone scan latency | < 60 s (Tier 2 flash with thinking) |
| JPL ephemeris load time | < 10 s (10 concurrent HTTP requests) |
| Frontend build size | < 20 MB chunks (Cesium isolated chunk) |
| Globe imagery | Real lunar surface, never blue void |

---

## 10. Data Sources

| Source | Usage |
|---|---|
| NASA LRO LOLA PDS archive | DEM calibration reference |
| NASA Moon Trek WMTS | Live globe imagery tiles |
| JPL Horizons API (ssd.jpl.nasa.gov) | Real Sun/Earth ephemeris per site |
| NASA ESMD site selection reports | Candidate site coordinates |

---

## 11. Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Google Gemini API access |
| `VITE_CESIUM_ION_TOKEN` | Optional | Cesium Ion (not used for imagery; retained for future terrain DEM upgrade) |

---

## 12. Out of Scope (v1.0)

- Real LRO LOLA DEM file parsing (synthetic calibrated DEM used instead)
- Multi-window Lunar/Earth mission support (single 30-day window only)
- User accounts or saved mission plans
- Mobile layout optimisation
- Offline / PWA mode
