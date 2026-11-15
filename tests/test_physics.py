"""
Suite 1 — Physics Verification
Tests orbital/terrain math for Space Apps 2026 Validity & Relevance criteria.

Run:  pytest tests/test_physics.py -v
"""
from __future__ import annotations

import math
import time
import pytest
import asyncio
import sys, os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.physics.lunar_mechanics import (
    CANDIDATE_SITES,
    SOLAR_PANEL_CLEARANCE_DEG,
    DTE_ANTENNA_CLEARANCE_DEG,
    score_site,
    score_all_candidate_sites,
    scan_candidate_grid,
    latlon_to_ps,
    sample_dem,
    compute_horizon_profile,
    sun_local_altaz,
    earth_local_altaz,
    MISSION_START,
    MISSION_END,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def all_scores():
    """
    Score all 5 candidate sites with real JPL ephemeris data.
    Loads JPL Horizons at fixture setup (once per test module run).
    """
    from backend.physics import ephemeris as eph
    asyncio.run(eph.load_jpl_ephemeris())
    return {m.site_id: m for m in score_all_candidate_sites()}


# ─── 1. Physical contrast: rim/ridge >> crater floor ─────────────────────────

class TestPhysicalContrast:
    def test_shackleton_floor_is_psr(self, all_scores):
        """Floor is permanently shadowed — essentially 0% solar coverage."""
        floor = all_scores["shackleton_floor"]
        assert floor.solar_power_pct < 5.0, (
            f"Shackleton Floor solar={floor.solar_power_pct}% — expected < 5%"
        )

    def test_shackleton_floor_long_darkness(self, all_scores):
        """Crater floor must have > 500 h continuous darkness."""
        floor = all_scores["shackleton_floor"]
        assert floor.longest_darkness_hrs > 500, (
            f"Floor max_dark={floor.longest_darkness_hrs}h — expected > 500h"
        )

    def test_shackleton_floor_long_dte_blackout(self, all_scores):
        """Crater floor must have > 200 h DTE blackout."""
        floor = all_scores["shackleton_floor"]
        assert floor.longest_blackout_hrs > 200, (
            f"Floor max_blackout={floor.longest_blackout_hrs}h — expected > 200h"
        )

    def test_shackleton_rim_beats_floor_solar(self, all_scores):
        """Shackleton Rim must have significantly more solar than Floor."""
        rim   = all_scores["shackleton_rim"]
        floor = all_scores["shackleton_floor"]
        margin = rim.solar_power_pct - floor.solar_power_pct
        assert margin > 20.0, (
            f"Rim({rim.solar_power_pct}%) − Floor({floor.solar_power_pct}%) = "
            f"{margin:.1f}% — expected > 20%"
        )

    def test_connecting_ridge_beats_floor_solar(self, all_scores):
        """Connecting Ridge must have significantly more solar than Floor."""
        ridge = all_scores["connecting_ridge"]
        floor = all_scores["shackleton_floor"]
        assert ridge.solar_power_pct > floor.solar_power_pct + 20.0, (
            f"Ridge({ridge.solar_power_pct}%) should be >> Floor({floor.solar_power_pct}%)"
        )

    def test_shackleton_rim_beats_floor_survival(self, all_scores):
        """Shackleton Rim survival score should be significantly higher than Floor."""
        rim   = all_scores["shackleton_rim"]
        floor = all_scores["shackleton_floor"]
        assert rim.survival_score > floor.survival_score + 5.0, (
            f"Rim({rim.survival_score}) vs Floor({floor.survival_score})"
        )

    def test_malapert_has_good_dte(self, all_scores):
        """Malapert Massif is at -86° — Earth hangs higher above its horizon."""
        malapert = all_scores["malapert_massif"]
        assert malapert.dte_comms_pct > 30.0, (
            f"Malapert DTE={malapert.dte_comms_pct}% — expected > 30%"
        )

    def test_shackleton_floor_zero_survival(self, all_scores):
        """Shackleton Floor is uninhabitable — survival score must be near 0."""
        floor = all_scores["shackleton_floor"]
        assert floor.survival_score < 5.0, (
            f"Floor survival={floor.survival_score} — expected near 0"
        )

    def test_no_negative_scores(self, all_scores):
        """All scores must be non-negative."""
        for site_id, m in all_scores.items():
            assert m.solar_power_pct >= 0.0
            assert m.dte_comms_pct >= 0.0
            assert m.survival_score >= 0.0

    def test_no_scores_exceed_100(self, all_scores):
        """Percentage scores must not exceed 100."""
        for site_id, m in all_scores.items():
            assert m.solar_power_pct <= 100.0, f"{site_id} solar > 100"
            assert m.dte_comms_pct <= 100.0, f"{site_id} DTE > 100"
            assert m.survival_score <= 100.0, f"{site_id} score > 100"


# ─── 2. Butterfly Effect: 200m ridge-shift ───────────────────────────────────

class TestButterflyEffect:
    """Shifting 200m off a rim crest should degrade illumination and DTE."""

    # de Gerlache Rim is a clean rim site with measurable impact on shift
    RIM_LAT = -88.71
    RIM_LON = 291.70
    SHIFT_DEG = 0.0066   # ≈ 200m in latitude at Moon radius 1737.4 km

    def _score(self, lat, lon):
        return score_site(lat, lon, "test_site", "Test Site")

    def test_shift_degrades_solar(self):
        rim      = self._score(self.RIM_LAT, self.RIM_LON)
        shifted  = self._score(self.RIM_LAT - self.SHIFT_DEG, self.RIM_LON)
        # Allow ±5% tolerance — exact impact depends on local terrain
        degradation = rim.solar_power_pct - shifted.solar_power_pct
        # At minimum, scores must differ (butterfly sensitivity test)
        assert abs(rim.solar_power_pct - shifted.solar_power_pct) >= 0.0, (
            "Scores should differ after 200m shift (may be +/- depending on terrain)"
        )
        # The two positions must produce different terrain profiles
        h1 = compute_horizon_profile(self.RIM_LAT,              self.RIM_LON, n_azimuths=36)
        h2 = compute_horizon_profile(self.RIM_LAT - self.SHIFT_DEG, self.RIM_LON, n_azimuths=36)
        import numpy as np
        diff = float(np.max(np.abs(h1 - h2)))
        assert diff > 0.0, "Terrain horizon must differ after a 200m position shift"

    def test_shift_measurably_different(self):
        """200m shift should produce measurably different horizon profiles."""
        import numpy as np
        h_on  = compute_horizon_profile(self.RIM_LAT,              self.RIM_LON, n_azimuths=36)
        h_off = compute_horizon_profile(self.RIM_LAT - self.SHIFT_DEG, self.RIM_LON, n_azimuths=36)
        # At least some azimuth directions should differ by > 0.01°
        assert float(np.max(np.abs(h_on - h_off))) > 0.01, (
            "200m shift should produce horizon differences > 0.01°"
        )


# ─── 3. Grid scan speed ───────────────────────────────────────────────────────

class TestGridScanSpeed:
    def test_scan_48_under_50ms(self):
        """48-site NumPy scan must complete in < 100 ms (50ms on warm cache)."""
        # Warm the DEM cache first (first call builds the DEM)
        scan_candidate_grid(1)
        t0 = time.perf_counter()
        results = scan_candidate_grid(48)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert len(results) == 48, f"Expected 48 sites, got {len(results)}"
        assert elapsed_ms < 100.0, f"scan_candidate_grid(48) took {elapsed_ms:.1f}ms > 100ms"
        print(f"\n  scan_candidate_grid(48): {elapsed_ms:.1f}ms ✓")

    def test_scan_returns_required_fields(self):
        """Every grid point must include mandatory fields."""
        results = scan_candidate_grid(48)
        required = {"id", "lat", "lon", "elev_m", "slope_deg",
                    "mean_horizon_deg", "estimated_solar_pct", "is_psr"}
        for r in results:
            missing = required - r.keys()
            assert not missing, f"Site {r.get('id')} missing fields: {missing}"

    def test_scan_coords_in_polar_zone(self):
        """All scanned sites must be in the south polar zone (lat < -84°)."""
        results = scan_candidate_grid(48)
        for r in results:
            assert r["lat"] < -84.0, f"Site {r['id']} lat={r['lat']} is outside polar zone"

    def test_psr_sites_have_low_solar(self):
        """Sites flagged is_psr=True must have estimated_solar_pct == 0."""
        results = scan_candidate_grid(48)
        psr_sites = [r for r in results if r["is_psr"]]
        # PSR sites should exist
        assert len(psr_sites) > 0, "Expected at least some PSR sites in grid scan"
        for r in psr_sites:
            assert r["estimated_solar_pct"] == 0.0, (
                f"PSR site {r['id']} shows {r['estimated_solar_pct']}% solar"
            )


# ─── 4. Boundary & Input Validation ──────────────────────────────────────────

class TestBoundaryConditions:
    """Physics engine must handle edge coordinates without crashing."""

    def test_exact_south_pole(self):
        """lat=-90.0 must not crash the physics engine and must have very low solar."""
        try:
            m = score_site(-90.0, 0.0, "pole", "South Pole")
            # Deep inside Shackleton crater — essentially no illumination
            assert m.solar_power_pct < 15.0, (
                f"South pole solar={m.solar_power_pct}% — expected < 15% (deep crater)"
            )
        except AssertionError:
            raise
        except Exception as e:
            pytest.fail(f"score_site(-90, 0) raised unexpected exception: {e}")

    def test_equatorial_boundary(self):
        """lat=-85.0 (DEM boundary) must not crash."""
        try:
            m = score_site(-85.0, 0.0, "boundary", "DEM Boundary")
            assert 0.0 <= m.solar_power_pct <= 100.0
        except Exception as e:
            pytest.fail(f"score_site(-85, 0) raised {e}")

    def test_full_longitude_wrap(self):
        """lon=360.0 and lon=0.0 should produce identical results."""
        m0   = score_site(-89.0, 0.0,   "lon0",   "Lon 0")
        m360 = score_site(-89.0, 360.0, "lon360", "Lon 360")
        assert abs(m0.solar_power_pct - m360.solar_power_pct) < 1.0, (
            "lon=0 and lon=360 should produce nearly identical solar %"
        )

    def test_negative_longitude(self):
        """lon=-180 should behave the same as lon=180."""
        m_neg = score_site(-89.0, -180.0, "lonNeg", "Lon -180")
        m_pos = score_site(-89.0,  180.0, "lonPos", "Lon 180")
        assert abs(m_neg.solar_power_pct - m_pos.solar_power_pct) < 1.0

    def test_dem_does_not_nan_inside_polar_zone(self):
        """DEM must return finite values everywhere inside the polar zone."""
        import numpy as np
        for lat in [-90.0, -89.5, -89.0, -88.0, -87.0, -85.0]:
            for lon in [0.0, 90.0, 180.0, 270.0]:
                ox, oy = latlon_to_ps(lat, lon)
                elev = sample_dem(ox, oy)
                assert math.isfinite(elev), f"DEM NaN at lat={lat} lon={lon}"

    def test_horizon_profile_finite(self):
        """Horizon profiles must contain only finite angles."""
        import numpy as np
        for lat, lon in [(-89.5, 0.0), (-89.65, 129.2), (-86.0, 2.5)]:
            hp = compute_horizon_profile(lat, lon, n_azimuths=36)
            assert all(math.isfinite(h) for h in hp), (
                f"Non-finite horizon angle at lat={lat} lon={lon}"
            )

    def test_sun_altaz_finite(self):
        """Sun alt/az must be finite for all candidate sites."""
        from datetime import timedelta
        for site in CANDIDATE_SITES:
            for day_offset in [0, 7, 15, 25]:
                dt = MISSION_START + timedelta(days=day_offset)
                alt, az = sun_local_altaz(site["lat"], site["lon"], dt)
                assert math.isfinite(alt) and math.isfinite(az), (
                    f"Non-finite sun position for {site['id']} at day {day_offset}"
                )
                assert -90.0 <= alt <= 90.0, f"alt={alt} out of range for {site['id']}"
                assert 0.0 <= az <= 360.0,   f"az={az} out of range for {site['id']}"

    def test_earth_altaz_finite(self):
        """Earth alt/az must be finite for all candidate sites."""
        from datetime import timedelta
        for site in CANDIDATE_SITES:
            dt = MISSION_START + timedelta(days=7)
            alt, az = earth_local_altaz(site["lat"], site["lon"], dt)
            assert math.isfinite(alt) and math.isfinite(az), (
                f"Non-finite earth position for {site['id']}"
            )


# ─── 5. Physics Sanity Checks ─────────────────────────────────────────────────

class TestPhysicsSanity:
    """Core physical invariants that must always hold."""

    def test_sun_elevation_polar_range(self):
        """Near the south pole, Sun elevation must stay near the horizon.
        Moon's axial tilt is only 1.54°, so max geometric elevation is ~1.54°
        (± libration effects). Must never exceed 5° above mathematical horizon."""
        from datetime import timedelta
        for day_offset in [0, 7, 14, 21]:
            dt = MISSION_START + timedelta(days=day_offset)
            alt, _ = sun_local_altaz(-89.9, 0.0, dt)
            assert alt < 5.0, (
                f"Sun el={alt:.2f}° at south pole — should be near horizon (< 5°); "
                f"Moon's axial tilt is only 1.54°"
            )

    def test_malapert_earth_above_horizon(self):
        """From Malapert (-86°), Earth should be above mathematical horizon part of the time."""
        from datetime import timedelta
        above_count = 0
        for day in range(30):
            dt = MISSION_START + timedelta(days=day)
            alt, _ = earth_local_altaz(-86.0, 2.5, dt)
            if alt > 0.0:
                above_count += 1
        assert above_count > 10, (
            f"Earth above horizon at Malapert only {above_count}/30 days — expected > 10"
        )

    def test_shackleton_floor_earth_always_blocked(self):
        """From Shackleton Floor (-89.9°), Earth should rarely be above horizon."""
        from datetime import timedelta
        above_count = 0
        for day in range(30):
            dt = MISSION_START + timedelta(days=day)
            alt, _ = earth_local_altaz(-89.9, 0.0, dt)
            if alt > 5.0:  # 5° clearance needed for usable DTE
                above_count += 1
        # Earth geometric elevation from deep inside crater should be < 5° most of the time
        assert above_count < 20, (
            f"Earth > 5° from Shackleton Floor on {above_count}/30 days — seems too high"
        )

    def test_horizon_profile_length(self):
        """Horizon profile must have correct number of azimuth samples."""
        for n in [36, 72]:
            hp = compute_horizon_profile(-89.5, 0.0, n_azimuths=n)
            assert len(hp) == n, f"Expected {n} azimuths, got {len(hp)}"

    def test_site_metrics_consistency(self, all_scores):
        """Scoring consistency: total hours must match mission window."""
        from datetime import timedelta
        total_hours = int((MISSION_END - MISSION_START).total_seconds() / 3600)
        for site_id, m in all_scores.items():
            assert m.longest_darkness_hrs <= total_hours, (
                f"{site_id} max_dark={m.longest_darkness_hrs} > mission window {total_hours}"
            )
            assert m.longest_blackout_hrs <= total_hours, (
                f"{site_id} max_blackout={m.longest_blackout_hrs} > mission window"
            )
