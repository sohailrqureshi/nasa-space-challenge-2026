"""
JPL Horizons ephemeris cache for SELENE SCOUT.
Author: Sohail Qureshi

Pre-fetches 720 hours of real Sun + Earth azimuth/elevation for each of the
5 Artemis candidate sites directly from NASA JPL Horizons
(https://ssd.jpl.nasa.gov/api/horizons.api).

Each site query uses CENTER='COORD@301' with the site's selenographic
coordinates so Horizons returns alt/az in the local topographic frame —
no additional coordinate transforms needed.

Two queries per site (Sun + Earth) = 10 async HTTP requests at startup.
Runs concurrently; typical wall-clock time: 3–6 s.

Falls back gracefully to the analytical model in lunar_mechanics.py if
the network is unavailable or any query fails.
"""

from __future__ import annotations

import asyncio
import logging
import math
import ssl
import time
import urllib.request
import urllib.parse
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── Mission window ────────────────────────────────────────────────────────────

_MISSION_START_STR = "2026-Nov-15 00:00"
_MISSION_STOP_STR  = "2026-Dec-15 01:00"   # +1 h buffer for end-of-window interpolation
_STEP              = "1 h"
_EXPECTED_HOURS    = 721                    # 720 intervals + 1 endpoint

# ── Cache structure ───────────────────────────────────────────────────────────

# Keyed by site_id → {"sun": (az_array, el_array), "earth": (az_array, el_array)}
# Arrays are float32 NumPy arrays of shape (_EXPECTED_HOURS,) in degrees.
_cache: Dict[str, Dict[str, Tuple[np.ndarray, np.ndarray]]] = {}
_jpl_loaded = False


# ── Site definitions ──────────────────────────────────────────────────────────
# (lon_east_deg, lat_deg, alt_km, site_id)
# lon/lat are selenographic; alt = 0 (topographic height handled by our DEM, not Horizons)

_SITES: List[Tuple[str, float, float]] = [
    ("shackleton_rim",   129.20, -89.65),   # rim peak latitude (PS radius ≈ 10.5 km)
    ("connecting_ridge", 222.50, -89.45),
    ("de_gerlache_rim",  291.70, -88.71),
    ("malapert_massif",    2.50, -86.00),
    ("shackleton_floor",   0.00, -89.90),
]

# ── JPL Horizons query ────────────────────────────────────────────────────────

def _query_horizons_sync(
    command: str,
    site_coord: str,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Blocking call to JPL Horizons OBSERVER table for a surface site on the Moon.

    command    : Horizons body code ('10' = Sun, '399' = Earth)
    site_coord : 'east_lon,lat,alt_km' selenographic coordinates

    Returns (azimuth_deg, elevation_deg) NumPy arrays for the mission window,
    or None on failure.

    Quantities='4' = Apparent azimuth (degrees) + elevation (degrees) in the
    local topographic frame, already accounting for the Moon's rotation.
    ELEV_CUT='-90' ensures entries are returned even below the horizon.
    """
    params = {
        "format": "text",
        "COMMAND": command,
        "CENTER": "COORD@301",          # surface observer on Moon (body 301)
        "SITE_COORD": site_coord,
        "MAKE_EPHEM": "YES",
        "TABLE_TYPE": "OBSERVER",
        "OBJ_DATA": "NO",
        "START_TIME": _MISSION_START_STR,
        "STOP_TIME":  _MISSION_STOP_STR,
        "STEP_SIZE":  _STEP,
        "QUANTITIES": "4",              # apparent azimuth, apparent elevation
        "ANG_FORMAT": "DEG",
        "EXTRA_PREC": "YES",
        "ELEV_CUT":   "-90",            # include below-horizon entries
    }
    url = "https://ssd.jpl.nasa.gov/api/horizons.api?" + urllib.parse.urlencode(params)

    def _fetch(ctx=None):
        kwargs = {"timeout": 30}
        if ctx is not None:
            kwargs["context"] = ctx
        with urllib.request.urlopen(url, **kwargs) as resp:
            return resp.read().decode("utf-8", errors="replace")

    text: str
    try:
        text = _fetch()
    except Exception as exc:
        # macOS Python may lack root certificates — retry with certifi bundle
        is_ssl_err = "CERTIFICATE_VERIFY_FAILED" in str(exc) or "SSL" in type(exc).__name__
        if is_ssl_err:
            try:
                import certifi
                ctx = ssl.create_default_context(cafile=certifi.where())
                text = _fetch(ctx)
            except Exception as exc2:
                logger.warning("JPL Horizons SSL error (command=%s): %s", command, exc2)
                return None
        else:
            logger.warning("JPL Horizons HTTP error (command=%s): %s", command, exc)
            return None

    start = text.find("$$SOE")
    end   = text.find("$$EOE")
    if start < 0 or end < 0:
        # Capture the first 400 chars of the response for diagnostics
        snippet = text[:400].replace("\n", " | ")
        logger.warning("No $$SOE/$$EOE in Horizons response (command=%s): %s", command, snippet)
        return None

    az_list: List[float] = []
    el_list: List[float] = []

    for line in text[start + 5 : end].strip().split("\n"):
        # Each line:  "YYYY-Mon-DD HH:MM  [flag]  azimuth  elevation"
        # The flag field ('*i', ' i', '* ', '  ') is not a float, so parsing
        # all float-shaped tokens reliably extracts only AZ and EL.
        floats = []
        for tok in line.split():
            try:
                floats.append(float(tok))
            except ValueError:
                pass
        if len(floats) >= 2:
            az_list.append(floats[-2])
            el_list.append(floats[-1])

    if len(az_list) < 2:
        logger.warning(
            "Too few data points from Horizons (command=%s, site=%s): got %d",
            command, site_coord, len(az_list),
        )
        return None

    return np.array(az_list, dtype=np.float32), np.array(el_list, dtype=np.float32)


_SEMAPHORE: Optional[asyncio.Semaphore] = None   # max 2 concurrent JPL requests
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0   # seconds between retries on 503


async def _fetch_one(
    loop: asyncio.AbstractEventLoop,
    command: str,
    site_coord: str,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Single query with retry on 503, behind the shared semaphore."""
    global _SEMAPHORE
    if _SEMAPHORE is None:
        _SEMAPHORE = asyncio.Semaphore(2)

    async with _SEMAPHORE:
        for attempt in range(1, _MAX_RETRIES + 1):
            result = await loop.run_in_executor(
                None, _query_horizons_sync, command, site_coord
            )
            if result is not None:
                return result
            if attempt < _MAX_RETRIES:
                logger.debug("Retry %d/%d for command=%s site=%s", attempt, _MAX_RETRIES, command, site_coord)
                await asyncio.sleep(_RETRY_DELAY)
        return None


async def _fetch_site(
    loop: asyncio.AbstractEventLoop,
    site_id: str,
    lon: float,
    lat: float,
) -> Optional[Dict[str, Tuple[np.ndarray, np.ndarray]]]:
    """
    Fetch Sun and Earth data for a single site (two sequential queries under the semaphore).
    Returns {"sun": (az, el), "earth": (az, el)} or None on failure.
    """
    site_coord = f"{lon:.4f},{lat:.4f},0"

    sun_data   = await _fetch_one(loop, "10",  site_coord)
    earth_data = await _fetch_one(loop, "399", site_coord)

    if sun_data is None or earth_data is None:
        logger.warning("Failed to load JPL data for site %s — will use analytical fallback", site_id)
        return None

    logger.info(
        "JPL loaded site %-20s  Sun: %d pts  Earth: %d pts",
        site_id, len(sun_data[0]), len(earth_data[0]),
    )
    return {"sun": sun_data, "earth": earth_data}


async def load_jpl_ephemeris() -> bool:
    """
    Pre-fetch JPL Horizons ephemeris for all 5 Artemis candidate sites.

    Uses a concurrency limit of 2 simultaneous requests (JPL rate limit).
    With retry on 503, all sites reliably load in ~10–20 s at startup.
    Populates the module-level _cache dict.  Returns True if at least one
    site loaded successfully; False if the network is completely unreachable.
    """
    global _cache, _jpl_loaded

    t0   = time.perf_counter()
    loop = asyncio.get_event_loop()

    tasks = [
        _fetch_site(loop, sid, lon, lat)
        for sid, lon, lat in _SITES
    ]
    results = await asyncio.gather(*tasks)

    successes = 0
    for (sid, _lon, _lat), data in zip(_SITES, results):
        if data is not None:
            _cache[sid] = data
            successes += 1

    elapsed_ms = (time.perf_counter() - t0) * 1000
    if successes > 0:
        _jpl_loaded = True
        logger.info(
            "JPL Horizons ephemeris ready: %d/%d sites loaded in %.0f ms",
            successes, len(_SITES), elapsed_ms,
        )
    else:
        logger.warning(
            "JPL Horizons completely unreachable (%.0f ms) — all sites using analytical fallback",
            elapsed_ms,
        )

    return _jpl_loaded


# ── Interpolated lookup ────────────────────────────────────────────────────────

def _hour_offset(dt_hour_utc: int) -> int:
    """Clamp a mission-window hour index to valid array bounds."""
    return max(0, min(_EXPECTED_HOURS - 1, dt_hour_utc))


def get_sun_altaz(
    site_id: str,
    mission_hour: float,
) -> Optional[Tuple[float, float]]:
    """
    Return (elevation_deg, azimuth_deg) for the Sun at a surface site.

    mission_hour : fractional hours since 2026-11-15T00:00Z (0 … 720)
    Returns None if JPL data is not cached for this site.
    """
    entry = _cache.get(site_id)
    if entry is None:
        return None
    az_arr, el_arr = entry["sun"]
    return _interp(az_arr, el_arr, mission_hour)


def get_earth_altaz(
    site_id: str,
    mission_hour: float,
) -> Optional[Tuple[float, float]]:
    """
    Return (elevation_deg, azimuth_deg) for Earth at a surface site.
    Returns None if JPL data is not cached for this site.
    """
    entry = _cache.get(site_id)
    if entry is None:
        return None
    az_arr, el_arr = entry["earth"]
    return _interp(az_arr, el_arr, mission_hour)


def _interp(
    az_arr: np.ndarray,
    el_arr: np.ndarray,
    h: float,
) -> Tuple[float, float]:
    """Linear interpolation with RA/360° wraparound handling for azimuth."""
    n  = len(az_arr)
    h  = max(0.0, min(n - 1.0, h))
    i0 = int(h)
    i1 = min(i0 + 1, n - 1)
    f  = h - i0

    el = float(el_arr[i0] + f * (el_arr[i1] - el_arr[i0]))

    az0, az1 = float(az_arr[i0]), float(az_arr[i1])
    diff = az1 - az0
    # Shortest-path interpolation across the 0°/360° seam
    if diff > 180.0:
        az1 -= 360.0
    elif diff < -180.0:
        az1 += 360.0
    az = (az0 + f * (az1 - az0)) % 360.0

    return el, az


def is_loaded() -> bool:
    return _jpl_loaded


def cache_summary() -> Dict[str, bool]:
    """Return dict of site_id → loaded for health checks."""
    return {sid: (sid in _cache) for sid, _, _ in _SITES}
