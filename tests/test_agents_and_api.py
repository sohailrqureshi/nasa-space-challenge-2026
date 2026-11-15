"""
Suite 2 — FastAPI & Live Gemini Agent Tests

Requires the backend to be running on http://localhost:8080 before running.
Start it with:
    cd /path/to/project && source .venv/bin/activate
    PYTHONPATH=. uvicorn backend.main:app --port 8080 &

Run:  pytest tests/test_agents_and_api.py -v -s
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import pytest
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://localhost:8080"
TIMEOUT  = 30.0   # seconds per request

# ── helpers ───────────────────────────────────────────────────────────────────

def api(path: str) -> str:
    return f"{BASE_URL}{path}"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as c:
        # Verify server is up before running any tests in this module
        try:
            r = c.get("/api/health")
            assert r.status_code == 200, f"Server not ready: {r.status_code}"
        except (httpx.ConnectError, httpx.ReadTimeout):
            pytest.skip("Backend not running on localhost:8080 — start with run-local.sh first")
        yield c


# ─── Health & Sites ───────────────────────────────────────────────────────────

class TestHealthAndSites:
    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["sites_cached"] == 5

    def test_health_reports_jpl(self, client):
        r = client.get("/api/health")
        data = r.json()
        # JPL status must be reported (may be True or False depending on network)
        assert "jpl_ephemeris" in data, "Health should report jpl_ephemeris status"
        assert "jpl_sites" in data

    def test_sites_returns_five(self, client):
        r = client.get("/api/sites")
        assert r.status_code == 200
        sites = r.json()
        assert len(sites) == 5

    def test_sites_have_required_fields(self, client):
        required = {
            "site_id", "name", "lat", "lon", "elev_m",
            "solar_power_pct", "dte_comms_pct", "survival_score",
            "longest_darkness_hrs", "longest_blackout_hrs",
            "horizon_profile", "terrain_slope_deg",
        }
        r = client.get("/api/sites")
        for site in r.json():
            missing = required - site.keys()
            assert not missing, f"Site {site.get('site_id')} missing: {missing}"

    def test_shackleton_floor_psr_metrics(self, client):
        r = client.get("/api/sites/shackleton_floor")
        assert r.status_code == 200
        m = r.json()
        assert m["solar_power_pct"] < 5.0,   f"Floor solar={m['solar_power_pct']}% — expected < 5%"
        assert m["longest_darkness_hrs"] > 500, f"Floor max_dark={m['longest_darkness_hrs']}h"
        assert m["dte_comms_pct"] == 0.0,      "Floor DTE should be 0%"

    def test_malapert_good_dte(self, client):
        r = client.get("/api/sites/malapert_massif")
        assert r.status_code == 200
        m = r.json()
        assert m["dte_comms_pct"] > 30.0, f"Malapert DTE={m['dte_comms_pct']}% — expected > 30%"

    def test_unknown_site_returns_404(self, client):
        r = client.get("/api/sites/nonexistent_base_alpha")
        assert r.status_code == 404


# ─── POST /api/command — Latency & Structured Output ─────────────────────────

JUDGE_QUERIES = [
    ("Fly to Shackleton Crater Rim and show sunlight",         "fly_to"),
    ("What happens if we land inside the crater floor?",       "none"),
    ("Compare Connecting Ridge vs Malapert Massif",            "compare_sites"),
    ("Give me a guided tour of the best landing spot",         "play_flythrough_tour"),
]

class TestCommandEndpoint:
    def _post_command(self, client, query: str):
        t0 = time.perf_counter()
        r = client.post("/api/command", json={"query": query})
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return r, elapsed_ms

    def test_fly_to_shackleton_command(self, client):
        q, expected_action = JUDGE_QUERIES[0]
        r, ms = self._post_command(client, q)
        assert r.status_code == 200, f"Command failed: {r.text}"
        data = r.json()
        assert data["action"] == expected_action, (
            f"Expected action={expected_action}, got {data['action']}"
        )
        assert len(data.get("response_text", "")) > 5
        print(f"\n  '{q}' → {data['action']}  {ms:.0f}ms")
        if ms > 2500:
            pytest.fail(f"Command latency {ms:.0f}ms > 2500ms threshold")

    def test_crater_floor_command(self, client):
        q, _ = JUDGE_QUERIES[1]
        r, ms = self._post_command(client, q)
        assert r.status_code == 200
        data = r.json()
        # Should give informative response about PSR
        assert len(data.get("response_text", "")) > 5
        assert data["action"] in {"none", "fly_to"}
        print(f"\n  '{q}' → {data['action']}  {ms:.0f}ms")

    def test_compare_sites_command(self, client):
        q, expected_action = JUDGE_QUERIES[2]
        r, ms = self._post_command(client, q)
        assert r.status_code == 200
        data = r.json()
        assert data["action"] == expected_action, (
            f"Expected {expected_action}, got {data['action']}"
        )
        # compare_sites must include both site IDs
        sites = data.get("sites") or []
        site_ids = [s.lower() for s in sites]
        has_ridge   = any("ridge" in s or "connecting" in s for s in site_ids)
        has_mal     = any("malapert" in s for s in site_ids)
        assert has_ridge and has_mal, f"compare_sites should reference both sites, got: {sites}"
        print(f"\n  '{q}' → {data['action']} sites={sites}  {ms:.0f}ms")
        if ms > 2500:
            pytest.fail(f"Command latency {ms:.0f}ms > 2500ms")

    def test_tour_command(self, client):
        q, expected_action = JUDGE_QUERIES[3]
        r, ms = self._post_command(client, q)
        assert r.status_code == 200
        data = r.json()
        assert data["action"] == expected_action, (
            f"Expected {expected_action}, got {data['action']}"
        )
        print(f"\n  '{q}' → {data['action']}  {ms:.0f}ms")

    def test_empty_query_returns_error(self, client):
        r = client.post("/api/command", json={"query": ""})
        assert r.status_code in {400, 422}, f"Expected 400 or 422, got {r.status_code}"

    def test_all_judge_queries_under_2500ms(self, client):
        """All 4 judge queries must collectively respond within budget."""
        for query, expected in JUDGE_QUERIES:
            r, ms = self._post_command(client, query)
            assert r.status_code == 200
            assert ms < 2500, f"'{query[:40]}' took {ms:.0f}ms > 2500ms"


# ─── GET /api/council/stream — SSE Concurrent Agents ─────────────────────────

class TestCouncilStream:
    def _collect_sse(self, client, site_id: str, timeout: float = 60.0):
        """Collect all SSE events from the council stream, return dict of agent→text."""
        events = {}
        t0 = time.perf_counter()
        with client.stream("GET", f"/api/council/stream?site_id={site_id}") as r:
            assert r.status_code == 200
            current_event = None
            current_data  = []
            for line in r.iter_lines():
                if time.perf_counter() - t0 > timeout:
                    break
                line = line.strip()
                if line.startswith("event:"):
                    current_event = line[6:].strip()
                    current_data  = []
                elif line.startswith("data:"):
                    try:
                        payload = json.loads(line[5:].strip())
                        current_data.append(payload.get("text", ""))
                    except json.JSONDecodeError:
                        pass
                elif line == "" and current_event:
                    if current_event != "done":
                        events.setdefault(current_event, []).extend(current_data)
                    else:
                        break
                    current_event = None
                    current_data  = []
        return {k: "".join(v) for k, v in events.items()}

    def test_all_three_agents_respond(self, client):
        events = self._collect_sse(client, "malapert_massif")
        required = {"power_officer", "comms_officer", "flight_director"}
        missing = required - events.keys()
        assert not missing, f"Missing agent events: {missing}. Got: {list(events.keys())}"

    def test_agents_produce_non_empty_text(self, client):
        events = self._collect_sse(client, "de_gerlache_rim")
        for agent, text in events.items():
            assert len(text) > 20, f"{agent} produced too short response: {repr(text)}"

    def test_power_officer_mentions_solar(self, client):
        events = self._collect_sse(client, "connecting_ridge")
        power_text = events.get("power_officer", "").lower()
        solar_keywords = {"solar", "power", "watt", "illuminat", "panel", "energy", "%"}
        assert any(kw in power_text for kw in solar_keywords), (
            f"Power Officer should mention solar metrics, got: {repr(power_text[:200])}"
        )

    def test_comms_officer_mentions_dte(self, client):
        events = self._collect_sse(client, "malapert_massif")
        comms_text = events.get("comms_officer", "").lower()
        comms_keywords = {"earth", "comms", "dte", "link", "antenna", "blackout", "signal"}
        assert any(kw in comms_text for kw in comms_keywords), (
            f"Comms Officer should mention DTE metrics, got: {repr(comms_text[:200])}"
        )

    def test_flight_director_delivers_verdict(self, client):
        events = self._collect_sse(client, "malapert_massif")
        fd_text = events.get("flight_director", "").lower()
        assert len(fd_text) > 20, "Flight Director must produce a non-trivial response"

    def test_shackleton_floor_council_caution(self, client):
        """Council should be cautious/negative about the PSR crater floor."""
        events = self._collect_sse(client, "shackleton_floor")
        all_text = " ".join(events.values()).lower()
        caution_keywords = {
            "shadow", "dark", "psr", "crater", "risk", "danger",
            "concern", "caution", "power", "survival"
        }
        assert any(kw in all_text for kw in caution_keywords), (
            f"Council should warn about PSR floor. Got: {repr(all_text[:300])}"
        )


# ─── POST /api/scan-zones — Batch Scout ──────────────────────────────────────

class TestScanZones:
    def test_scan_zones_returns_top3(self, client):
        r = client.post("/api/scan-zones", timeout=120.0)
        assert r.status_code == 200, f"scan-zones failed: {r.text[:200]}"
        data = r.json()
        assert "top_sites" in data, "Response must have top_sites key"
        sites = data["top_sites"]
        assert len(sites) == 3, f"Expected 3 ranked sites, got {len(sites)}"

    def test_scan_zones_sorted_by_rank(self, client):
        r = client.post("/api/scan-zones", timeout=120.0)
        sites = r.json()["top_sites"]
        ranks = [s["rank"] for s in sites]
        assert ranks == [1, 2, 3], f"Sites not sorted by rank: {ranks}"

    def test_scan_zones_valid_coordinates(self, client):
        r = client.post("/api/scan-zones", timeout=120.0)
        for site in r.json()["top_sites"]:
            lat = site["lat"]
            lon = site["lon"]
            assert -90.0 <= lat <= -84.0, f"lat={lat} outside polar zone"
            assert 0.0 <= lon <= 360.0,   f"lon={lon} out of range"
            assert 0.0 <= site["overall_score"] <= 100.0

    def test_scan_zones_no_psr_rank1(self, client):
        r = client.post("/api/scan-zones", timeout=120.0)
        sites = r.json()["top_sites"]
        rank1 = next(s for s in sites if s["rank"] == 1)
        # Rank-1 site should not be a PSR (deep crater floor)
        # We check by latitude: PSR sites are very deep at lat < -89.8°
        assert rank1["lat"] > -89.95, f"Rank-1 site is likely PSR at lat={rank1['lat']}"

    def test_scan_zones_has_mission_summary(self, client):
        r = client.post("/api/scan-zones", timeout=120.0)
        data = r.json()
        assert len(data.get("mission_summary", "")) > 20

    def test_scan_zones_response_time(self, client):
        t0 = time.perf_counter()
        r = client.post("/api/scan-zones", timeout=120.0)
        ms = (time.perf_counter() - t0) * 1000
        assert r.status_code == 200
        print(f"\n  scan-zones latency: {ms:.0f}ms")
        assert ms < 60000, f"scan-zones took {ms:.0f}ms > 60s"


# ─── Fault Tolerance ──────────────────────────────────────────────────────────

class TestFaultTolerance:
    def test_malformed_json_body_returns_422(self, client):
        r = client.post(
            "/api/command",
            content=b"not-json",
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422

    def test_missing_query_field_returns_422(self, client):
        r = client.post("/api/command", json={"wrong_field": "hello"})
        assert r.status_code == 422

    def test_council_stream_unknown_site_returns_404(self, client):
        r = client.get("/api/council/stream?site_id=bogus_site")
        assert r.status_code == 404

    def test_scan_zones_idempotent_on_repeat(self, client):
        """Two consecutive scans should both succeed and return 3 sites."""
        r1 = client.post("/api/scan-zones", timeout=120.0)
        r2 = client.post("/api/scan-zones", timeout=120.0)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert len(r1.json()["top_sites"]) == 3
        assert len(r2.json()["top_sites"]) == 3
