"""Geocoding helpers + Haversine nearest-neighbor."""

from __future__ import annotations

import math
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Simple process-local cache to avoid amplifying outbound Nominatim calls.
_GEOCODE_CACHE: Dict[str, Tuple[float, Tuple[float, float]]] = {}
_GEOCODE_CACHE_TTL_S = 3600.0
_GEOCODE_CACHE_MAX = 256
# Cap live Nominatim fan-out from chat/MCP (cache misses only).
_GEOCODE_MAX_QUERY_LEN = 120
_GEOCODE_MIN_INTERVAL_S = 1.0
_GEOCODE_MAX_MISSES_PER_WINDOW = 30
_GEOCODE_WINDOW_S = 60.0
_GEOCODE_LAST_CALL_S = 0.0
_GEOCODE_MISS_TIMES: List[float] = []


class GeocodeError(Exception):
    """Geocoding failed or returned no results."""


class GeocodeRateLimitError(GeocodeError):
    """Too many distinct geocode requests in a short window."""


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def clear_geocode_cache() -> None:
    _GEOCODE_CACHE.clear()
    _GEOCODE_MISS_TIMES.clear()
    global _GEOCODE_LAST_CALL_S
    _GEOCODE_LAST_CALL_S = 0.0


def geocode_place(
    place: str,
    session: Optional[requests.Session] = None,
    timeout: float = 20.0,
) -> Tuple[float, float]:
    global _GEOCODE_LAST_CALL_S
    query = (place or "").strip()
    if not query:
        raise GeocodeError("empty place string")
    if len(query) > _GEOCODE_MAX_QUERY_LEN:
        raise GeocodeError(
            f"place string too long (max {_GEOCODE_MAX_QUERY_LEN} characters)"
        )
    cache_key = query.lower()
    now = time.time()
    cached = _GEOCODE_CACHE.get(cache_key)
    if cached and now - cached[0] < _GEOCODE_CACHE_TTL_S:
        return cached[1]

    # Rate-limit cache misses (process-local; shared by chat + MCP).
    cutoff = now - _GEOCODE_WINDOW_S
    while _GEOCODE_MISS_TIMES and _GEOCODE_MISS_TIMES[0] < cutoff:
        _GEOCODE_MISS_TIMES.pop(0)
    if len(_GEOCODE_MISS_TIMES) >= _GEOCODE_MAX_MISSES_PER_WINDOW:
        raise GeocodeRateLimitError(
            "geocode rate limit exceeded; try again shortly or use a known city name"
        )
    elapsed = now - _GEOCODE_LAST_CALL_S
    if _GEOCODE_LAST_CALL_S and elapsed < _GEOCODE_MIN_INTERVAL_S:
        time.sleep(_GEOCODE_MIN_INTERVAL_S - elapsed)

    sess = session or requests.Session()
    _GEOCODE_LAST_CALL_S = time.time()
    _GEOCODE_MISS_TIMES.append(_GEOCODE_LAST_CALL_S)
    resp = sess.get(
        NOMINATIM_URL,
        params={"q": query, "format": "json", "limit": 1},
        headers={"User-Agent": "OpenCRE-owasp-agent/1.0 (research)"},
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise GeocodeError(f"geocoder HTTP {resp.status_code}")
    data = resp.json()
    if not isinstance(data, list) or not data:
        raise GeocodeError(f"no geocode result for {query!r}")
    lat = float(data[0]["lat"])
    lon = float(data[0]["lon"])
    coords = (lat, lon)
    if len(_GEOCODE_CACHE) >= _GEOCODE_CACHE_MAX:
        # Drop an arbitrary oldest-ish entry (dict preserves insertion order).
        _GEOCODE_CACHE.pop(next(iter(_GEOCODE_CACHE)))
    _GEOCODE_CACHE[cache_key] = (now, coords)
    return coords


def nearest_by_coords(
    origin: Tuple[float, float],
    candidates: Iterable[Dict[str, Any]],
    lat_key: str = "latitude",
    lon_key: str = "longitude",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    lat0, lon0 = origin
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for item in candidates:
        lat = item.get(lat_key)
        lon = item.get(lon_key)
        if lat is None or lon is None:
            continue
        try:
            dist = haversine_km(lat0, lon0, float(lat), float(lon))
        except (TypeError, ValueError):
            continue
        row = dict(item)
        row["distance_km"] = round(dist, 2)
        scored.append((dist, row))
    scored.sort(key=lambda x: x[0])
    return [row for _, row in scored[:limit]]
