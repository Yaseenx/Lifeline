from __future__ import annotations
"""Route geometry + on-route traffic signals from public, KEYLESS services:
OSRM for the road route, OpenStreetMap Overpass for `highway=traffic_signals`.

stdlib only (urllib) — same style as geocode.py. All calls are blocking, so the
async wrapper runs them in a thread-pool executor; they must NEVER be called
from the 10 Hz engine tick. For production, self-host OSRM + an Overpass mirror.
"""
import asyncio
import json
import math
import ssl
import urllib.parse
import urllib.request

# Use an unverified SSL context to bypass TLS certificate/handshake verification 
# failures in this restricted local environment.
try:
    _SSL_CTX = ssl._create_unverified_context()
except AttributeError:
    _SSL_CTX = ssl.create_default_context()

# Offline fallback dataset — consulted ONLY when the live fetch yields nothing.
# If local_signals or its dataset file is absent, it returns [] and behaviour is
# identical to before (no change to the live path).
try:
    import local_signals
except Exception:  # pragma: no cover - the fallback is optional
    local_signals = None

# Use HTTP (not HTTPS) because the system Python 3.9 ships with LibreSSL 2.8.3
# which cannot negotiate TLS with these servers (SSLV3_ALERT_HANDSHAKE_FAILURE).
# These are public, keyless demo services so HTTP is fine for the demo.
OSRM = "http://router.project-osrm.org/route/v1/driving"
OVERPASS = [
    "http://overpass-api.de/api/interpreter",
    "http://lz4.overpass-api.de/api/interpreter",
    "http://z.overpass-api.de/api/interpreter",
]
MAX_OFFSET_M = 45.0   # a signal must be this close to the route to count as "on" it
MERGE_M = 25.0        # collapse signals clustered at one junction
TIMEOUT_S = 5.0       # per-mirror cap — fail fast to the local dataset, don't hang the corridor


def _get(url: str, data: bytes | None = None, headers: dict | None = None) -> str:
    h = dict(headers or {})
    h.setdefault("User-Agent", "LifeLine/1.0 (emergency corridor; contact ops)")  # OSM/OSRM expect a UA
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return r.read().decode("utf-8", "replace")


def _haversine(a, b) -> float:
    R = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _project(p, a, b):
    k = math.cos(math.radians(a[0]))
    bx = (b[1] - a[1]) * k
    by = b[0] - a[0]
    px = (p[1] - a[1]) * k
    py = p[0] - a[0]
    l2 = bx * bx + by * by or 1e-12
    t = max(0.0, min(1.0, (px * bx + py * by) / l2))
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def _cumulative(path):
    cum = [0.0]
    for i in range(1, len(path)):
        cum.append(cum[-1] + _haversine(path[i - 1], path[i]))
    return cum


def signals_on_path(path):
    """Every mapped traffic signal within MAX_OFFSET_M of the route, nearest-first,
    tagged with distance-along-route. path = [(lat,lng), ...]."""
    if len(path) < 2:
        return []
    lats = [p[0] for p in path]
    lngs = [p[1] for p in path]
    s, n, w, e = min(lats), max(lats), min(lngs), max(lngs)
    pad = 0.002
    q = (f'[out:json][timeout:25];node["highway"="traffic_signals"]'
         f'({s - pad},{w - pad},{n + pad},{e + pad});out;')
    body = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for url in OVERPASS:
        try:
            txt = _get(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
            if not txt.lstrip().startswith("{"):
                raise RuntimeError("overpass busy")
            els = json.loads(txt).get("elements", [])
            cum = _cumulative(path)
            found = []
            for el in els:
                if el.get("type") != "node":
                    continue
                p = (el["lat"], el["lon"])
                best, along = 1e9, 0.0
                for i in range(len(path) - 1):
                    snap = _project(p, path[i], path[i + 1])
                    d = _haversine(p, snap)
                    if d < best:
                        best = d
                        along = cum[i] + _haversine(path[i], snap)
                if best <= MAX_OFFSET_M:
                    found.append({"lat": p[0], "lng": p[1], "along": along})
            found.sort(key=lambda x: x["along"])
            merged = []
            for sg in found:
                if not merged or sg["along"] - merged[-1]["along"] > MERGE_M:
                    merged.append(sg)
            return merged
        except Exception as ex:  # noqa: BLE001 — try the next mirror
            last = ex
    raise RuntimeError(f"overpass unavailable: {last}")


def route_geometry(o_lat, o_lng, d_lat, d_lng):
    """OSRM road route as [(lat,lng), ...] (keyless demo server)."""
    url = f"{OSRM}/{o_lng},{o_lat};{d_lng},{d_lat}?overview=full&geometries=geojson"
    data = json.loads(_get(url))
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(data.get("message") or "no route")
    coords = data["routes"][0]["geometry"]["coordinates"]
    return [(c[1], c[0]) for c in coords]


def _route_and_signals_blocking(o_lat, o_lng, d_lat, d_lng):
    path = route_geometry(o_lat, o_lng, d_lat, d_lng)
    # LOCAL-FIRST: the local dataset is instant (no network), so the corridor's signals
    # appear immediately. Only reach out to the (slow, public) Overpass mirrors when the
    # local dataset doesn't cover this route well — and prefer the live result only if it
    # is richer. Build the full dataset (tools/build_signals_dataset.py) for instant
    # coverage everywhere; then Overpass is never on the critical path.
    local = local_signals.signals_on_path_local(path) if local_signals is not None else []
    signals = local
    if len(local) < 2:
        try:
            live = signals_on_path(path)
            if live and len(live) >= len(signals):
                signals = live
        except Exception as e:
            print(f"live_signals: overpass unavailable, using local dataset ({e})")
    return signals, [{"lat": p[0], "lng": p[1]} for p in path]


async def route_and_signals(o_lat, o_lng, d_lat, d_lng):
    """(signals, path). signals = [{lat,lng,along}], path = [{lat,lng}]. Never
    call from the tick — this does blocking network I/O in a worker thread."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _route_and_signals_blocking, o_lat, o_lng, d_lat, d_lng)
