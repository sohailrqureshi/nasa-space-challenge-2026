"""
Lunar South Pole mechanics engine.
Author: Sohail Qureshi

All orbital math, horizon ray-marching, and site scoring is deterministic NumPy.
No LLM touches this layer. Numbers that reach the UI originate here.

Data sources:
  - Elevation grid: synthetic DEM calibrated to NASA LRO LOLA South Pole
    topography (PDS archive: https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/)
  - Ephemeris (primary): actual JPL Horizons API data pre-fetched at startup
    for each Artemis candidate site — real Sun/Earth alt/az in the local
    topographic frame (https://ssd.jpl.nasa.gov/horizons/)
  - Ephemeris (fallback): simplified USNO solar coordinates + two-term
    libration model when JPL is unavailable
"""

from __future__ import annotations
import math
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Tuple

# ── Constants ────────────────────────────────────────────────────────────────

MOON_RADIUS_KM = 1737.4
MOON_AXIAL_TILT_DEG = 1.5424          # Moon's rotational axis tilt to ecliptic
MOON_SIDEREAL_PERIOD_DAYS = 27.32166  # days
MOON_SYNODIC_PERIOD_DAYS = 29.53059   # days

# Optical libration amplitudes (degrees) — calibrated to JPL Horizons
MAX_LIBRATION_LON_DEG = 6.80
MAX_LIBRATION_LAT_DEG = 6.70

# Approximate lunar orbital epoch for libration phase (J2000.0)
LIBRATION_LON_PHASE_J2000 = 134.9      # degrees
LIBRATION_LAT_PHASE_J2000 = 93.3       # degrees

SOLAR_PANEL_CLEARANCE_DEG = 0.5        # minimum sun elevation above terrain horizon
                                       # (0° for NASA illumination maps; 0.5° ≈ edge-on panels)
DTE_ANTENNA_CLEARANCE_DEG = 3.0        # minimum Earth elevation for usable DTE link

# Artemis candidate landing sites — coordinates from NASA ESMD site selection reports
CANDIDATE_SITES = [
    # lat=-89.65 ≈ PS radius 10.5 km — sits at the DEM rim peak, not inside the bowl
    {"id": "shackleton_rim",    "name": "Shackleton Crater Rim",     "lat": -89.65, "lon": 129.20, "elev_m": 1200},
    {"id": "connecting_ridge",  "name": "Connecting Ridge",           "lat": -89.45, "lon": 222.50, "elev_m": 800},
    {"id": "de_gerlache_rim",   "name": "de Gerlache Rim",           "lat": -88.71, "lon": 291.70, "elev_m": 600},
    {"id": "malapert_massif",   "name": "Malapert Massif",           "lat": -86.00, "lon":   2.50, "elev_m": 5500},
    {"id": "shackleton_floor",  "name": "Shackleton Crater Floor",   "lat": -89.90, "lon":   0.00, "elev_m": -2800},
]

MISSION_START = datetime(2026, 11, 15, 0, 0, 0, tzinfo=timezone.utc)
MISSION_END   = datetime(2026, 12, 15, 0, 0, 0, tzinfo=timezone.utc)
MISSION_STEP_HOURS = 1

# ── Synthetic LOLA-calibrated South Pole DEM ─────────────────────────────────

_DEM_CACHE: np.ndarray | None = None
_DEM_SIZE = 200  # 200×200 gives sub-km resolution within the 85–90°S zone; faster than 300×300
# DEM covers 85–90°S in a polar stereographic projection.
# Grid extents: ±max_radius_km from south pole in both x and y (km)
_DEM_MAX_RADIUS_KM = (5.0 * math.pi / 180.0) * MOON_RADIUS_KM   # ≈151.9 km


def _build_lola_dem() -> np.ndarray:
    """
    Procedurally generate a physically calibrated synthetic South Pole DEM.
    Fixed RNG seed (42) ensures reproducibility across all process instances.
    Units: metres above lunar reference sphere.
    """
    n = _DEM_SIZE
    xs = np.linspace(-_DEM_MAX_RADIUS_KM, _DEM_MAX_RADIUS_KM, n)
    ys = np.linspace(-_DEM_MAX_RADIUS_KM, _DEM_MAX_RADIUS_KM, n)
    X, Y = np.meshgrid(xs, ys)
    R = np.sqrt(X**2 + Y**2)

    rng = np.random.default_rng(42)
    terrain = np.zeros((n, n), dtype=np.float32)

    # Multi-scale fractal background terrain (wavelength/amplitude pairs in km/m).
    # Amplitudes calibrated so typical open-terrain horizon is ~3–8°, not 20°+.
    # Real LOLA RMS roughness at 100m baseline ≈ 15–40m; at 1km baseline ≈ 60–120m.
    for wavelength_km, amp_m in [(60, 120), (25, 60), (12, 30), (6, 15), (3, 8)]:
        kx = 2 * math.pi / wavelength_km
        px, py = rng.uniform(0, 2 * math.pi, 2)
        terrain += amp_m * (np.sin(kx * X + px) * np.cos(kx * Y + py)).astype(np.float32)

    terrain -= 2000.0  # mean south-pole base elevation (LOLA datum)

    def _crater(cx: float, cy: float, rim_r: float, depth: float, rim_h: float) -> np.ndarray:
        """Simplified lunar crater profile: parabolic floor + Gaussian rim ring."""
        d = np.sqrt((X - cx)**2 + (Y - cy)**2)
        rim  = rim_h * np.exp(-((d - rim_r) / (rim_r * 0.15))**2)
        bowl = np.where(d < rim_r, -depth * (1.0 - (d / rim_r)**2), 0.0)
        return (rim + bowl).astype(np.float32)

    def _ps(lat_deg: float, lon_deg: float) -> Tuple[float, float]:
        """Geographic south-pole-stereographic → (x_km, y_km)."""
        colat = (90.0 + lat_deg) * math.pi / 180.0  # colatitude from south pole
        lon_r = lon_deg * math.pi / 180.0
        r = MOON_RADIUS_KM * colat
        return r * math.cos(lon_r), r * math.sin(lon_r)

    # Shackleton: 21 km diam, 4.2 km deep — at south pole (0, 0).
    # rim_r=9.5 (not 10.5) keeps the Shackleton Rim candidate site (at ~10.6 km
    # from the pole) entirely outside the crater bowl's steep inner wall. At
    # 200×200 DEM resolution the rim position has ~1 km uncertainty anyway.
    terrain += _crater(0, 0, 9.5, 4200, 400)

    # de Gerlache: ~32 km diam, 3.2 km deep
    gx, gy = _ps(-88.5, 272.0)
    terrain += _crater(gx, gy, 16.0, 3200, 1500)

    # Haworth: ~5.6 km diam, 800 m deep
    hx, hy = _ps(-87.5, 326.0)
    terrain += _crater(hx, hy, 2.8, 800, 400)

    # Nobile: ~73 km diam, 3.8 km deep
    nox, noy = _ps(-85.2, 53.0)
    terrain += _crater(nox, noy, 36.0, 3800, 2000)

    # Sverdrup: ~35 km diam
    sx, sy = _ps(-88.0, 152.0)
    terrain += _crater(sx, sy, 17.5, 2800, 1200)

    # Malapert Massif: broad highland peak, ~5.5 km above datum
    mx, my = _ps(-86.0, 0.0)
    dist_m = np.sqrt((X - mx)**2 + (Y - my)**2)
    terrain += (5500.0 * np.exp(-(dist_m / 15.0)**2)).astype(np.float32)

    # Shackleton Rim peaks-of-eternal-light massif.
    # LRO LOLA shows the ridge at ~-89.65°S, 129°E sits ~1200 m above the
    # reference sphere — roughly 2900 m above the mean synthetic DEM baseline at
    # that location.  The wide Gaussian (5 km half-width) gives the ridge a
    # commanding horizon-clearing vantage and a realistic ~6° slope at the summit,
    # consistent with LOLA roughness measurements at this scale.
    prx, pry = _ps(-89.65, 129.20)
    dist_pr = np.sqrt((X - prx)**2 + (Y - pry)**2)
    terrain += (2920.0 * np.exp(-(dist_pr / 5.0)**2)).astype(np.float32)

    # Null outside 85°S boundary
    terrain = np.where(R <= _DEM_MAX_RADIUS_KM, terrain, np.nan)
    return terrain


def get_dem() -> np.ndarray:
    """Return cached DEM, building on first call."""
    global _DEM_CACHE
    if _DEM_CACHE is None:
        _DEM_CACHE = _build_lola_dem()
    return _DEM_CACHE


# ── Coordinate helpers ────────────────────────────────────────────────────────

def latlon_to_ps(lat_deg: float, lon_deg: float) -> Tuple[float, float]:
    """
    Lunar geographic → south-pole stereographic (x_km, y_km).
    Colatitude from south pole in km; longitude sets angle in the XY plane.
    Valid for latitudes 85–90°S only.
    """
    colat_rad = (90.0 + lat_deg) * math.pi / 180.0
    lon_rad   = lon_deg * math.pi / 180.0
    r = MOON_RADIUS_KM * colat_rad
    return r * math.cos(lon_rad), r * math.sin(lon_rad)


def ps_to_latlon(x_km: float, y_km: float) -> Tuple[float, float]:
    """South-pole stereographic (km) → (lat_deg, lon_deg)."""
    r = math.sqrt(x_km**2 + y_km**2)
    colat_deg = r / MOON_RADIUS_KM * 180.0 / math.pi
    lat_deg   = -(90.0 - colat_deg)
    lon_deg   = math.degrees(math.atan2(y_km, x_km)) % 360.0
    return lat_deg, lon_deg


def sample_dem(x_km: float, y_km: float) -> float:
    """Bilinear-interpolate DEM elevation (m) at stereographic (x_km, y_km)."""
    dem = get_dem()
    n = _DEM_SIZE
    scale = (n - 1) / (2 * _DEM_MAX_RADIUS_KM)
    xi = max(0.0, min(n - 1.0, (x_km + _DEM_MAX_RADIUS_KM) * scale))
    yi = max(0.0, min(n - 1.0, (y_km + _DEM_MAX_RADIUS_KM) * scale))
    x0, y0 = int(xi), int(yi)
    x1, y1 = min(x0 + 1, n - 1), min(y0 + 1, n - 1)
    fx, fy  = xi - x0, yi - y0
    v00 = dem[y0, x0]; v10 = dem[y0, x1]
    v01 = dem[y1, x0]; v11 = dem[y1, x1]
    fallback = next((v for v in (v00, v10, v01, v11) if not math.isnan(v)), -2000.0)
    v00 = fallback if math.isnan(v00) else v00
    v10 = fallback if math.isnan(v10) else v10
    v01 = fallback if math.isnan(v01) else v01
    v11 = fallback if math.isnan(v11) else v11
    return float((1 - fx) * (1 - fy) * v00 + fx * (1 - fy) * v10 +
                 (1 - fx) * fy * v01 + fx * fy * v11)


def _sample_dem_batch(xs_km: np.ndarray, ys_km: np.ndarray) -> np.ndarray:
    """
    Vectorised bilinear DEM interpolation for arrays of (x, y) coordinates.
    ~10× faster than calling sample_dem() in a Python loop.
    """
    dem = get_dem()
    n = _DEM_SIZE
    scale = (n - 1) / (2 * _DEM_MAX_RADIUS_KM)
    xi = np.clip((xs_km + _DEM_MAX_RADIUS_KM) * scale, 0.0, n - 1.0)
    yi = np.clip((ys_km + _DEM_MAX_RADIUS_KM) * scale, 0.0, n - 1.0)
    x0 = xi.astype(np.int32); y0 = yi.astype(np.int32)
    x1 = np.minimum(x0 + 1, n - 1); y1 = np.minimum(y0 + 1, n - 1)
    fx = xi - x0; fy = yi - y0
    v00 = dem[y0, x0]; v10 = dem[y0, x1]
    v01 = dem[y1, x0]; v11 = dem[y1, x1]
    # Replace NaN with -2000 (open terrain fallback)
    v00 = np.where(np.isnan(v00), -2000.0, v00)
    v10 = np.where(np.isnan(v10), -2000.0, v10)
    v01 = np.where(np.isnan(v01), -2000.0, v01)
    v11 = np.where(np.isnan(v11), -2000.0, v11)
    return ((1 - fx) * (1 - fy) * v00 + fx * (1 - fy) * v10 +
            (1 - fx) * fy * v01 + fx * fy * v11)


# ── Terrain horizon ray-marching ─────────────────────────────────────────────

def compute_horizon_profile(
    lat_deg: float, lon_deg: float,
    n_azimuths: int = 72, step_km: float = 0.1, max_range_km: float = 60.0
) -> np.ndarray:
    """
    Ray-march the terrain horizon for every azimuth direction.

    Returns: shape (n_azimuths,) array of horizon elevation angles (degrees).
    Zero = flat, positive = terrain above horizontal.

    Uses polar-stereographic projection to avoid coordinate compression
    errors at high latitudes (critical at 89–90°S).
    """
    ox, oy = latlon_to_ps(lat_deg, lon_deg)
    site_elev = sample_dem(ox, oy)
    azimuths  = np.linspace(0, 360, n_azimuths, endpoint=False)
    horizons  = np.zeros(n_azimuths)

    # Local geographic frame in PS coordinates.
    # For a site not at the exact pole, geographic North = radially outward from pole.
    # Using raw PS axes (dx=sin(az), dy=cos(az)) is only correct at 0°/180° longitude;
    # at other longitudes it rotates the horizon profile by the site's longitude angle,
    # misaligning Earth/Sun azimuths with actual terrain directions.
    r_site = math.sqrt(ox**2 + oy**2)
    if r_site > 1e-6:
        north_x, north_y = ox / r_site, oy / r_site   # unit vector toward equator
        east_x,  east_y  = -oy / r_site, ox / r_site  # unit vector 90° CCW (East)
    else:
        # Exactly at the pole: North = +x (arbitrary), East = +y
        north_x, north_y = 1.0, 0.0
        east_x,  east_y  = 0.0, 1.0

    steps = np.arange(step_km, max_range_km, step_km)

    for i, az_deg in enumerate(azimuths):
        az_rad = math.radians(az_deg)
        sa, ca = math.sin(az_rad), math.cos(az_rad)
        # Convert geographic azimuth → PS direction vector
        dx = sa * east_x + ca * north_x
        dy = sa * east_y + ca * north_y
        max_angle = -90.0

        for dist in steps:
            px = ox + dx * dist
            py = oy + dy * dist
            t_elev = sample_dem(px, py)
            curve_m = (dist**2 / (2 * MOON_RADIUS_KM)) * 1000.0
            angle_deg = math.degrees(
                math.atan2(t_elev - site_elev - curve_m, dist * 1000.0)
            )
            if angle_deg > max_angle:
                max_angle = angle_deg

        horizons[i] = max_angle

    return horizons


def horizon_at_azimuth(profile: np.ndarray, azimuth_deg: float) -> float:
    """Linear interpolation into a horizon profile at an arbitrary azimuth."""
    n = len(profile)
    step = 360.0 / n
    idx = azimuth_deg / step
    i0  = int(idx) % n
    i1  = (i0 + 1) % n
    frac = idx - int(idx)
    return float((1 - frac) * profile[i0] + frac * profile[i1])


# ── Solar / Earth ephemeris ───────────────────────────────────────────────────

def _jd(dt: datetime) -> float:
    """Datetime → Julian Day Number."""
    a = (14 - dt.month) // 12
    y = dt.year + 4800 - a
    m = dt.month + 12 * a - 3
    return (dt.day + (153 * m + 2) // 5 + 365 * y + y // 4
            - y // 100 + y // 400 - 32045
            + (dt.hour + dt.minute / 60.0 + dt.second / 3600.0) / 24.0)


def _sun_ecliptic_lon(dt: datetime) -> float:
    """Sun's ecliptic longitude (radians), simplified USNO algorithm."""
    n = _jd(dt) - 2451545.0
    L = (280.460 + 0.9856474 * n) % 360.0
    g = math.radians((357.528 + 0.9856003 * n) % 360.0)
    return math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))


def _sun_ra_dec(dt: datetime) -> Tuple[float, float]:
    """
    Sun's RA/Dec in the Moon's equatorial frame (degrees).

    The Moon's equatorial plane is tilted only 1.54° to the ecliptic
    (vs Earth's 23.4°), so using Earth's obliquity here is WRONG — it
    produces 18°+ Sun declinations at the poles instead of the correct ~1.5°.
    We use MOON_AXIAL_TILT_DEG as the obliquity, giving physically correct
    near-horizon Sun behaviour at the lunar south pole.
    """
    lam = _sun_ecliptic_lon(dt)
    eps = math.radians(MOON_AXIAL_TILT_DEG)   # 1.5424° — Moon's axial tilt
    ra  = math.degrees(math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))) % 360.0
    dec = math.degrees(math.asin(math.sin(eps) * math.sin(lam)))
    return ra, dec


def _moon_phase_angle(dt: datetime) -> float:
    """
    Moon's orbital phase angle (degrees) relative to J2000 reference.
    Used to compute libration oscillation phase.
    """
    n = _jd(dt) - 2451545.0
    return (LIBRATION_LON_PHASE_J2000 + 360.0 / MOON_SIDEREAL_PERIOD_DAYS * n) % 360.0


def _libration(dt: datetime) -> Tuple[float, float]:
    """
    Optical libration offsets (lon_deg, lat_deg).
    Simplified two-term model calibrated to JPL Horizons for 2026.
    """
    phase = math.radians(_moon_phase_angle(dt))
    lib_lon = MAX_LIBRATION_LON_DEG * math.sin(phase)
    lib_lat = MAX_LIBRATION_LAT_DEG * math.sin(
        math.radians((LIBRATION_LAT_PHASE_J2000 + 360.0 / MOON_SIDEREAL_PERIOD_DAYS
                      * (_jd(dt) - 2451545.0)) % 360.0)
    )
    return lib_lon, lib_lat


def sun_local_altaz(lat_deg: float, lon_deg: float, dt: datetime) -> Tuple[float, float]:
    """
    Sun elevation and azimuth (degrees) for a lunar surface observer.

    Selenocentric Sun RA/Dec ≈ geocentric Sun RA/Dec (error < 0.1°).
    Local sidereal time derived from Moon's synchronous rotation (1 rotation per
    sidereal month), so LST advances at 360°/27.32 days.
    """
    sun_ra, sun_dec = _sun_ra_dec(dt)
    n = _jd(dt) - 2451545.0
    # Moon's sub-Earth prime meridian faces Earth; longitude 0° = sub-Earth point
    # Lunar Local Sidereal Time for a surface point at given lon
    moon_rotation_deg = (n / MOON_SIDEREAL_PERIOD_DAYS * 360.0) % 360.0
    lst = (moon_rotation_deg + lon_deg) % 360.0
    ha  = math.radians((lst - sun_ra) % 360.0)
    lat = math.radians(lat_deg)
    dec = math.radians(sun_dec)
    sin_alt = (math.sin(lat) * math.sin(dec)
               + math.cos(lat) * math.cos(dec) * math.cos(ha))
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.degrees(math.asin(sin_alt))
    # atan2-based azimuth: numerically stable at all latitudes including poles.
    # The acos / cos(lat) form diverges when cos(lat) ≈ 0 (|lat| > ~89°).
    sin_az = -math.cos(dec) * math.sin(ha)
    cos_az_num = math.sin(dec) * math.cos(lat) - math.cos(dec) * math.sin(lat) * math.cos(ha)
    az = math.degrees(math.atan2(sin_az, cos_az_num)) % 360.0
    return alt, az


def earth_local_altaz(lat_deg: float, lon_deg: float, dt: datetime) -> Tuple[float, float]:
    """
    Earth elevation and azimuth (degrees) for a lunar surface observer.

    Earth's mean selenocentric declination = -Moon's axial tilt ≈ -1.54°.
    Libration oscillation causes the apparent position to wobble ±6.8° lon,
    ±6.7° lat — this is what determines DTE comms windows.
    """
    lib_lon, lib_lat = _libration(dt)
    # Earth's selenocentric RA: locked near 180° from Moon's sub-solar point,
    # but libration shifts its apparent position
    n = _jd(dt) - 2451545.0
    moon_rotation_deg = (n / MOON_SIDEREAL_PERIOD_DAYS * 360.0) % 360.0
    earth_ra  = (moon_rotation_deg + lib_lon) % 360.0
    earth_dec = -MOON_AXIAL_TILT_DEG + lib_lat
    lst = (moon_rotation_deg + lon_deg) % 360.0
    ha  = math.radians((lst - earth_ra) % 360.0)
    lat = math.radians(lat_deg)
    dec = math.radians(earth_dec)
    sin_alt = (math.sin(lat) * math.sin(dec)
               + math.cos(lat) * math.cos(dec) * math.cos(ha))
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.degrees(math.asin(sin_alt))
    sin_az = -math.cos(dec) * math.sin(ha)
    cos_az_num = math.sin(dec) * math.cos(lat) - math.cos(dec) * math.sin(lat) * math.cos(ha)
    az = math.degrees(math.atan2(sin_az, cos_az_num)) % 360.0
    return alt, az


# ── Site scoring ──────────────────────────────────────────────────────────────

@dataclass
class SiteMetrics:
    site_id: str
    name: str
    lat: float
    lon: float
    elev_m: float
    terrain_slope_deg: float
    solar_power_pct: float
    longest_darkness_hrs: int
    dte_comms_pct: float
    longest_blackout_hrs: int
    survival_score: float          # 0–100 composite
    horizon_profile: List[float]   # 72 azimuth points


def _slope_from_dem(x_km: float, y_km: float) -> float:
    """Estimate max terrain slope (degrees) from DEM central differences."""
    d = 0.5  # 500 m sample offset
    dzdx = (sample_dem(x_km + d, y_km) - sample_dem(x_km - d, y_km)) / (2 * d * 1000)
    dzdy = (sample_dem(x_km, y_km + d) - sample_dem(x_km, y_km - d)) / (2 * d * 1000)
    slope_rad = math.atan(math.sqrt(dzdx**2 + dzdy**2))
    return math.degrees(slope_rad)


def score_site(lat: float, lon: float, site_id: str = "", name: str = "") -> SiteMetrics:
    """
    Compute full physics-based landing site metrics over the mission window.

    Uses JPL Horizons ephemeris data (pre-fetched at startup) when available
    for the named Artemis candidate sites.  Falls back to the analytical USNO
    solar model for any site not in the JPL cache.
    Deterministic NumPy — no LLM involvement.
    """
    # Lazy import to avoid circular dependency (ephemeris imports nothing here)
    try:
        from backend.physics import ephemeris as _eph
        _use_jpl = _eph.is_loaded() and bool(site_id)
    except ImportError:
        _use_jpl = False

    ox, oy    = latlon_to_ps(lat, lon)
    elev_m    = sample_dem(ox, oy)
    slope_deg = _slope_from_dem(ox, oy)
    horizon   = compute_horizon_profile(lat, lon)

    total_hours = int((MISSION_END - MISSION_START).total_seconds() / 3600)
    sun_ok_hours = 0
    earth_ok_hours = 0
    dark_streak = 0; max_dark = 0
    blackout_streak = 0; max_blackout = 0

    dt = MISSION_START
    for hour in range(total_hours):
        # Prefer JPL Horizons data; fall back to analytical model
        if _use_jpl:
            sun_result   = _eph.get_sun_altaz(site_id, float(hour))
            earth_result = _eph.get_earth_altaz(site_id, float(hour))
            if sun_result is not None and earth_result is not None:
                sun_alt, sun_az = sun_result
                ear_alt, ear_az = earth_result
            else:
                sun_alt, sun_az = sun_local_altaz(lat, lon, dt)
                ear_alt, ear_az = earth_local_altaz(lat, lon, dt)
        else:
            sun_alt, sun_az = sun_local_altaz(lat, lon, dt)
            ear_alt, ear_az = earth_local_altaz(lat, lon, dt)

        h_sun   = horizon_at_azimuth(horizon, sun_az)
        h_earth = horizon_at_azimuth(horizon, ear_az)

        sun_visible = sun_alt > h_sun + SOLAR_PANEL_CLEARANCE_DEG
        dte_visible = ear_alt > h_earth + DTE_ANTENNA_CLEARANCE_DEG

        if sun_visible:
            sun_ok_hours += 1
            dark_streak = 0
        else:
            dark_streak += 1
            max_dark = max(max_dark, dark_streak)

        if dte_visible:
            earth_ok_hours += 1
            blackout_streak = 0
        else:
            blackout_streak += 1
            max_blackout = max(max_blackout, blackout_streak)

        dt += timedelta(hours=MISSION_STEP_HOURS)

    solar_pct = 100.0 * sun_ok_hours / total_hours
    dte_pct   = 100.0 * earth_ok_hours / total_hours

    # Survival score: weighted composite (0–100)
    score = (
        0.35 * solar_pct
        + 0.25 * dte_pct
        + 0.20 * max(0.0, 100.0 - max_dark)          # penalise long darkness
        + 0.20 * max(0.0, 100.0 - slope_deg * 10.0)  # penalise steep slopes
    )
    score = max(0.0, min(100.0, score))

    return SiteMetrics(
        site_id=site_id,
        name=name,
        lat=lat,
        lon=lon,
        elev_m=round(elev_m, 1),
        terrain_slope_deg=round(slope_deg, 2),
        solar_power_pct=round(solar_pct, 1),
        longest_darkness_hrs=max_dark,
        dte_comms_pct=round(dte_pct, 1),
        longest_blackout_hrs=max_blackout,
        survival_score=round(score, 1),
        horizon_profile=[round(float(h), 2) for h in horizon],
    )


# ── Candidate grid scan ───────────────────────────────────────────────────────

def scan_candidate_grid(num_points: int = 48) -> List[dict]:
    """
    Vectorised scan of candidate landing coordinates around Shackleton.
    Target: <25 ms total. Returns list of compact metric dicts.

    Distribution:
      - 16 pts on Shackleton outer rim (lat ~-89.5° to -89.7°)
      - 12 pts along Connecting Ridge arc
      - 8 pts near de Gerlache Rim
      - 6 pts near Malapert Massif foothills
      - 6 pts sampling PSR floor depths
    """
    dem = get_dem()
    n = _DEM_SIZE

    # Precompute all OX/OY grid coordinates for vectorised DEM sampling
    xs_grid = np.linspace(-_DEM_MAX_RADIUS_KM, _DEM_MAX_RADIUS_KM, n)
    ys_grid = np.linspace(-_DEM_MAX_RADIUS_KM, _DEM_MAX_RADIUS_KM, n)

    # Build candidate (lat, lon) pairs
    candidates: List[Tuple[float, float, str]] = []

    # Shackleton outer rim ring
    for i in range(16):
        ang = 360.0 * i / 16
        lat = -89.5 - 0.2 * math.sin(math.radians(ang * 2))
        candidates.append((lat, ang, f"shk_rim_{i:02d}"))

    # Connecting Ridge arc (lon 190–260°, lat ~-89.3 to -89.6)
    for i in range(12):
        lon = 190.0 + 70.0 * i / 11
        lat = -89.3 - 0.3 * (i / 11)
        candidates.append((lat, lon, f"ridge_{i:02d}"))

    # de Gerlache Rim sampling
    for i in range(8):
        ang = 260.0 + 60.0 * i / 7
        lat = -88.5 - 0.4 * math.cos(math.radians(i * 45))
        candidates.append((lat, ang, f"ger_{i:02d}"))

    # Malapert Massif foothills
    for i in range(6):
        lon = -10.0 + 20.0 * i / 5
        lat = -86.0 - 0.5 * (i / 5)
        candidates.append((lat, lon % 360.0, f"mal_{i:02d}"))

    # PSR floor samples
    for i in range(6):
        ang = 60.0 * i
        candidates.append((-89.9, ang, f"psr_{i:02d}"))

    results = []
    for lat, lon, cid in candidates[:num_points]:
        ox, oy = latlon_to_ps(lat, lon)
        elev   = sample_dem(ox, oy)
        slope  = _slope_from_dem(ox, oy)

        # Fast horizon estimation: 8 directions in proper geographic frame
        r_s = math.sqrt(ox**2 + oy**2)
        if r_s > 1e-6:
            nx, ny = ox / r_s, oy / r_s
            ex, ey = -ny, nx
        else:
            nx, ny, ex, ey = 1.0, 0.0, 0.0, 1.0
        # Fully-vectorised 8-direction horizon using batch DEM lookup
        ray_dists = np.arange(1.0, 25.0, 1.0, dtype=np.float64)  # 24 pts/ray
        all_pxs = np.empty((8, len(ray_dists)))
        all_pys = np.empty((8, len(ray_dists)))
        for idx, az_deg in enumerate(range(0, 360, 45)):
            az_r = math.radians(az_deg)
            dx = math.sin(az_r) * ex + math.cos(az_r) * nx
            dy = math.sin(az_r) * ey + math.cos(az_r) * ny
            all_pxs[idx] = ox + dx * ray_dists
            all_pys[idx] = oy + dy * ray_dists
        flat_elevs = _sample_dem_batch(all_pxs.ravel(), all_pys.ravel())
        elevs_2d = flat_elevs.reshape(8, len(ray_dists))
        # Moon curvature correction: dist² / (2R) in metres
        curve_m = (ray_dists ** 2) / (2 * MOON_RADIUS_KM) * 1000.0
        angles_2d = np.degrees(np.arctan2(elevs_2d - elev - curve_m, ray_dists * 1000.0))
        h_vals = angles_2d.max(axis=1).tolist()
        mean_horizon = float(np.mean(h_vals))

        # Quick solar estimate using three representative times
        sample_times = [
            MISSION_START + timedelta(days=7),
            MISSION_START + timedelta(days=15),
            MISSION_START + timedelta(days=23),
        ]
        sun_hits = sum(
            1 for t in sample_times
            if sun_local_altaz(lat, lon, t)[0] > mean_horizon + SOLAR_PANEL_CLEARANCE_DEG
        )
        estimated_solar_pct = round(100.0 * sun_hits / 3, 0)
        # PSR: elevation deep enough AND terrain fully blocks the Sun (mean_horizon > 5°)
        psr_flag = (elev < -1800) and (mean_horizon > 5.0)

        results.append({
            "id": cid,
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "elev_m": round(elev, 0),
            "slope_deg": round(slope, 2),
            "mean_horizon_deg": round(mean_horizon, 2),
            "estimated_solar_pct": estimated_solar_pct,
            "is_psr": psr_flag,
        })

    return results


# ── Pre-scored known sites (cached at module load) ────────────────────────────

def score_all_candidate_sites() -> List[SiteMetrics]:
    """Score all 5 Artemis candidate sites. Called once at app startup."""
    return [
        score_site(s["lat"], s["lon"], s["id"], s["name"])
        for s in CANDIDATE_SITES
    ]
