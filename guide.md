# SELENE SCOUT — User Guide

**SELENE SCOUT** is a 3D lunar mission planning tool for the 2026 NASA Space Apps Challenge, built by **Sohail Qureshi**. It lets you evaluate Artemis candidate landing sites at the lunar south pole using real ephemeris data, physics-accurate terrain analysis, and a live AI Mission Control Council.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ (only needed if rebuilding the frontend)
- A Google Gemini API key

### 1. Set up your environment file

Create a `.env` file in the project root:

```
GEMINI_API_KEY=your_gemini_api_key_here
VITE_CESIUM_ION_TOKEN=your_cesium_ion_token_here   # optional
```

### 2. Launch with the run script

```bash
chmod +x run-local.sh
./run-local.sh
```

This script:
- Creates a Python virtual environment in `.venv/`
- Installs all dependencies from `requirements.txt`
- Starts the FastAPI server on port 8080
- Fetches live JPL Horizons ephemeris for all 5 candidate sites at startup

### 3. Open the app

Navigate to [http://localhost:8080](http://localhost:8080) in a Chromium-based browser (Chrome, Edge, Arc). Firefox is supported but WebGL performance may vary.

---

## The Briefing Screen

When the app loads you will see the **Mission Briefing** modal over the globe, which already shows real lunar surface imagery from NASA LRO WAC.

Three one-click demos are available for judges:

| Demo | What it does |
|---|---|
| **Scan Shackleton Rim** | Triggers an AI radar sweep of 48 candidate sites → drops 3 ranked landing pins on the globe |
| **Simulate Comms Blackout** | Flies into Shackleton Crater Floor (0% DTE), accelerates the timeline → Earth disappears below the horizon |
| **Compare 200m Ridge Shift** | Autonomous flythrough comparing a shadowed depression vs. a sunlit ridge peak 200 m away |

Click **Start Exploring →** to enter the main interface.

---

## Main Interface

The screen has four regions:

```
┌──────────────────────────────────────┬──────────────────────┐
│                                      │  COMMAND BAR         │
│         3D MOON GLOBE                │  SITE LIST           │
│                                      │                      │
├──────────────────────────────────────┤                      │
│  MISSION CONTROL COUNCIL             │                      │
│  Power · Comms · Flight Director     │                      │
├──────────────────────────────────────┴──────────────────────┤
│  TIMELINE SCRUBBER                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Selecting a Landing Site

Click any site in the **ARTEMIS CANDIDATE SITES** panel on the right. The globe flies to that site and the sidebar shows:

- **Score** (0–100): weighted composite of solar, comms, and terrain
- **Solar illumination %**: fraction of the 30-day mission window the site receives sunlight
- **DTE availability %**: fraction of time the site has line-of-sight to Earth
- **Max darkness**: longest continuous night in hours
- **Max comms blackout**: longest continuous Earth-invisible window in hours
- **Terrain slope**: average slope in degrees (> 15° is a landing risk)
- **Elevation**: metres above lunar reference sphere

The score colours give a quick read:
- **Green (≥ 50):** viable candidate
- **Orange (20–49):** caution — review trade-offs
- **Red (< 20 or 0):** mission-critical concern (likely a Permanently Shadowed Region)

---

## Mission Control Council

After selecting a site, click the **Mission Council** button. Three AI agents stream their analysis in parallel:

### Power Officer
Analyses solar power viability. Covers:
- Illumination fraction and power budget implications
- Longest darkness interval and thermal survival risk
- Concrete recommendation (panel orientation, battery sizing, or site shift)

### Comms Officer
Analyses Direct-to-Earth communications. Covers:
- DTE availability percentage and antenna geometry requirements
- Longest communication blackout and mission impact
- Mitigation options (relay satellite, comms schedule, or location adjustment)

### Flight Director
Delivers the overall Go / Caution / No-Go verdict. TARS-inspired tone:
- Single strongest supporting data point for the verdict
- What would flip the verdict
- A dry remark about why humans keep proposing crater floors

All three agents use only the physics-computed numbers — they cannot invent data.

---

## Natural Language Command Bar

Type any plain-English command in the **NATURAL LANGUAGE COMMAND** field (top right) and press Enter or click →. The command is parsed by `gemini-3.5-flash-lite` with a < 500 ms target response time. The result appears as spoken feedback in the HUD status bar, and the globe or timeline responds immediately.

---

### Navigation commands

These fly the camera to a site and select it in the sidebar.

| What you type | What happens |
|---|---|
| `Fly to Shackleton Rim` | Camera flies to Shackleton Crater Rim at −89.65°S, selects it, starts telemetry panel |
| `Go to Malapert Massif` | Camera flies to Malapert Massif at −86°S, the highest-solar site |
| `Take me to Connecting Ridge` | Camera flies to the Connecting Ridge site (score 42, best flat terrain) |
| `Show de Gerlache Rim` | Navigates to de Gerlache Rim, known for wide Earth visibility |
| `Navigate to the crater floor` | Flies to Shackleton Crater Floor — the PSR no-go reference site |
| `Show me the worst comms site` | Flies to Shackleton Crater Floor with a cautionary spoken note about its 0 % DTE |

**Expected response:** The top bar shows the agent's spoken line (e.g. `"Initiating descent profile toward Shackleton Crater Rim. High solar illumination detected."`) and the globe flies to that site within ~2.5 seconds. The right panel populates with scores and telemetry cards.

---

### Site comparison commands

Ask the agent to contrast two named sites directly.

| What you type | What happens |
|---|---|
| `Compare Shackleton Rim and Connecting Ridge` | Flies to Shackleton Rim and streams a spoken comparison of both sites |
| `Compare the two rim sites` | Interprets this as Shackleton Rim vs. de Gerlache Rim; flies to the first |
| `What is the trade-off between Malapert and Connecting Ridge?` | Flies to Malapert and delivers a narrated trade-off (solar vs. slope) |

**Expected response:** The top bar shows a one-sentence comparison (e.g. `"Shackleton offers exceptional solar power as an Artemis favourite, while Connecting Ridge provides superior communications access."`) and the globe flies to the first named site.

> **Note:** Questions like "Which site has the best solar power?" or "Which site is safest?" are interpreted as scan requests and trigger the 48-point zone scan rather than a direct verbal answer. If you want a direct answer, name the specific sites you want to compare.

---

### Timeline commands

The command bar can start and speed up playback, but scrubbing to a specific date must be done with the slider.

| What you type | What happens |
|---|---|
| `Play at 1000x speed` | Sets multiplier to 1 000× and starts playback; sightline indicators update in real time |
| `Play at 100x speed` | Sets multiplier to 100× and starts playback |
| `Start the simulation` | Starts playback at the current speed |

**Expected response:** The ▶ button activates, the timeline scrubber begins moving, and the SUN / EARTH indicators in the bottom bar update live.

> **Limitation:** "Jump to November 25", "Pause the timeline", and "Reset mission time" return informational text but do not move the clock — the agent directs you to use the slider for those operations. Use the scrubber or the ▶ button directly for date navigation and pause/resume.

---

### Zone scan and AI analysis commands

These trigger backend AI operations and may take 5–30 seconds.

| What you type | What happens |
|---|---|
| `Scan for the best landing site` | Triggers the full 48-point zone scan; radar animation plays on the globe |
| `Run the AI scan` | Same as above — alias recognised |
| `Find me the top 3 sites near the south pole` | Runs the scan and returns ranked gold/silver/bronze pins |
| `Scan zones` | Shortest recognised trigger for the zone scan |

**Expected response:** The Scan 48 button pulses `Scanning 48 zones…` while `gemini-3.8-flash` reasons over the grid. When complete, up to 3 ranked pins appear on the globe and the HUD displays a summary like `"Top site: Connecting Ridge (score 42). Shackleton Rim 2nd (33). de Gerlache Rim 3rd (30)."` Typical latency is 5–30 s.

---

### Sightline and physics questions

Ask qualitative questions about any of the five sites.

| What you type | What happens |
|---|---|
| `Is the sun visible at Shackleton Rim right now?` | Top bar answers: `"Shackleton Crater Rim offers high solar illumination. The sun is currently above the local horizon."` |
| `Can we talk to Earth from de Gerlache Rim?` | Spoken line about DTE visibility at de Gerlache |
| `How long is the next comms blackout at Malapert?` | Qualitative answer about Malapert's near-continuous Earth link |
| `What is the slope at Connecting Ridge?` | Spoken note that Connecting Ridge has a moderate slope suitable for traverse |
| `Is Shackleton Floor permanently shadowed?` | Confirms: `"Yes, Shackleton Crater Floor is a permanently shadowed region… but lacking solar power."` |

**Expected response:** The top bar shows a spoken one-liner. These are qualitative answers — the agent knows each site's characteristics from the system prompt. For exact numbers (slope degrees, blackout hours) use the telemetry cards in the right panel after selecting the site.

> **Note:** Physics questions return `action: none` — the globe does not fly and no site is selected. The only output is the spoken text in the top bar.

---

### Tour and presentation commands

Useful for demos and judges.

| What you type | What happens |
|---|---|
| `Play a flythrough tour of all sites` | Globe hops to all 5 sites in score order, 4 s dwell at each; right panel updates at every stop |
| `Give me the judge demo` | Interpreted as a scan request — triggers the full 48-point zone scan |
| `Show me the crater` | Shorthand for flying to Shackleton Crater Floor — the visual centrepiece |

**Expected response:** Top bar shows `"Initiating automated flythrough tour across all lunar south pole landing sites. Enjoy the views."` The camera flies to each site in turn — Connecting Ridge → Malapert Massif → Shackleton Rim → de Gerlache Rim → Shackleton Floor — pausing 4 seconds at each so you can read the telemetry. Click any site pin or type a new command to interrupt the tour.

> **Limitation:** "Fly a polar orbit" is not recognised — the agent responds with an informational note directing you to select a surface landing site instead.

---

### Tips for best results

- **Be specific with site names.** The model recognises all five full names and common shorthands: `Shackleton Rim`, `Connecting Ridge`, `de Gerlache`, `Malapert`, `crater floor`.
- **Navigation and comparison commands cause the globe to fly.** Questions and physics queries return a spoken answer in the top bar but do not move the camera.
- **"Which site is best at X?" triggers a scan.** If you want a direct verbal answer, name two specific sites: `Compare Malapert and Connecting Ridge`.
- **Date scrubbing uses the slider, not the command bar.** Type `play at 1000x speed` to fast-forward, but drag the scrubber for specific dates.
- **The spoken response always appears in the top bar.** After any command the agent's one-liner replaces the site-coords readout. It persists until the next command or site selection.
- **Physics questions are fast; scan questions are slow.** `fly_to` and `compare_sites` respond in < 500 ms. Zone scans invoke a Gemini thinking model and take 5–30 s.
- **If the command bar is silent**, check that `GEMINI_API_KEY` is set in `.env` — the command agent requires a live API connection.

---

## Timeline Scrubber

The bar at the bottom controls mission time (15 Nov – 15 Dec 2026).

| Control | Function |
|---|---|
| ▶ Play button | Start time animation |
| **1×** | Real time (mostly for demonstration) |
| **100×** | 100× speed — good for watching day/night cycles |
| **1000×** | 1 000× speed — good for running the full 30-day window quickly |
| Scrub slider | Drag to any point in the mission window |

The date display shows the current simulated UTC time. At 1 000× one pass through the 30-day window takes about 2.6 seconds.

---

## Understanding the Site Scores

Scores are computed entirely from physics (no AI guessing):

```
score = 0.5 × solar_pct
      + 0.3 × dte_pct
      + 0.2 × (1 − slope / 15)
      − 25  × is_psr_penalty
      − slope_excess_penalty
```

**Shackleton Crater Floor scores 0** because it is a Permanently Shadowed Region (PSR) — no sunlight ever reaches it. This is intentional and accurate. It is included as a contrast case to show why crater interiors are mission killers despite their water-ice interest.

**Malapert Massif scores highest on solar** (near-continuous illumination due to elevation and open horizon) but is farther from the pole — a real trade-off mission planners face.

---

## Zone Scanner (AI Radar Sweep)

The **Scan Shackleton Rim** demo (or typing `scan zones` in the command bar) runs the full autonomous zone scan:

1. A 48-point NumPy grid is computed across 85–90°S
2. PSR sites and slopes > 15° are automatically eliminated
3. A Gemini model with extended thinking reasons over the full matrix
4. The top 3 sites are returned with ranked pins dropped on the globe (gold / silver / bronze)

Typical latency: 5–30 seconds depending on Gemini API load.

---

## Running the Test Suite

```bash
# Activate the virtual environment
source .venv/bin/activate

# Suite 1: Physics engine unit tests
pytest tests/test_physics.py -v

# Suite 2: FastAPI + live Gemini agent tests (requires server running)
pytest tests/test_agents_and_api.py -v

# Suite 3: Playwright E2E tests (requires server running + Playwright browsers)
pytest tests/e2e_local_judge_flow.py -v

# All suites
pytest tests/ -v
```

The E2E suite includes globe imagery regression tests that verify the globe renders actual lunar surface pixels (not the blue void or plain grey).

---

## Troubleshooting

**Globe shows as solid blue:**
The Cesium Ion token is likely missing or Vite could not read it. Confirm `.env` is in the project root (not `frontend/`). The app still loads a grey fallback and NASA Moon Trek imagery even without an Ion token.

**"JPL Horizons unavailable" in startup logs:**
The JPL API is rate-limited. The backend falls back to an analytical ephemeris. All site scores will still be computed — they will use USNO solar coordinates rather than live JPL data. Accuracy difference is typically < 1–2% for the solar fraction metric.

**Council agents show no text:**
Check that `GEMINI_API_KEY` is set correctly in `.env`. The backend logs a warning on startup if the key is missing or invalid.

**Command bar returns no response:**
Same root cause — verify `GEMINI_API_KEY`. The command bar requires a live Gemini API connection.

**Zone scan times out:**
The scan uses a Gemini model with extended thinking. On a slow connection or under API quota pressure it can exceed 60 seconds. Retry after a few seconds.
