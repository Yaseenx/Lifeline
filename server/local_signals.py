from __future__ import annotations
"""OFFLINE traffic-signal source — the fail-safe fallback for the green corridor.

When the live Overpass fetch (live_signals.signals_on_path) is unavailable — no
internet, a blocked TLS handshake, or every mirror busy — the corridor would
otherwise have no on-route signals. This module loads a local, cross-checked
dataset of Chennai traffic signals (data/signals_chennai.geojson, produced by
tools/build_signals_dataset.py) and returns the signals that lie on a route in
exactly the same shape live_signals uses: [{"lat","lng","along"}], nearest-first.

Design guarantees (so nothing already working is affected):
  • It is only ever consulted as a FALLBACK by live_signals.
  • If the dataset file is missing or unreadable, every function returns [] —
    i.e. behaviour is identical to today (an empty green wave; the route still
    draws). No exception ever escapes.
  • stdlib only; pure functions; no network; safe to import anywhere.
"""
import json
import math
import os

MAX_OFFSET_M = 45.0   # a signal must be this close to the route to count as "on" it (matches live_signals)
MERGE_M = 25.0        # collapse signals clustered at one junction (matches live_signals)

_DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "signals_chennai.geojson")

_points: list[tuple[float, float]] | None = None   # cache: [(lat, lng), ...]
_features: list[dict] | None = None                # cache: [{lat,lng,name,controller,source}]
_loaded_from: str | None = None
_mtime: float | None = None


def _maybe_reset() -> None:
    """If the dataset file changed on disk (e.g. the builder rewrote it), drop the
    caches so the next read reflects the new data — no server restart needed."""
    global _points, _features, _mtime
    try:
        m = os.path.getmtime(_DATA_PATH)
    except OSError:
        m = None
    if m != _mtime:
        _mtime = m
        _points = None
        _features = None


def _load() -> list[tuple[float, float]]:
    """Load & cache the local signal points. Returns [] on any problem."""
    global _points, _loaded_from
    _maybe_reset()
    if _points is not None:
        return _points
    pts: list[tuple[float, float]] = []
    try:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            gj = json.load(f)
        for feat in gj.get("features", []):
            geom = feat.get("geometry") or {}
            if geom.get("type") != "Point":
                continue
            c = geom.get("coordinates") or []
            if len(c) >= 2 and isinstance(c[0], (int, float)) and isinstance(c[1], (int, float)):
                pts.append((float(c[1]), float(c[0])))  # GeoJSON is [lng, lat]
        _loaded_from = _DATA_PATH
    except Exception:
        pts = []            # missing/corrupt file -> behave exactly as "no signals"
    _points = pts
    return _points


def all_features() -> list[dict]:
    """Every mapped signal as {lat,lng,name,controller,source} — for the ops map's
    placeholder layer. Returns [] if the dataset is missing/corrupt. Never raises."""
    global _features
    _maybe_reset()
    if _features is not None:
        return list(_features)
    feats: list[dict] = []
    try:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            gj = json.load(f)
        for feat in gj.get("features", []):
            geom = feat.get("geometry") or {}
            if geom.get("type") != "Point":
                continue
            c = geom.get("coordinates") or []
            if len(c) >= 2 and isinstance(c[0], (int, float)) and isinstance(c[1], (int, float)):
                pr = feat.get("properties") or {}
                feats.append({"lat": float(c[1]), "lng": float(c[0]),
                              "name": pr.get("name", "signal"),
                              "controller": bool(pr.get("controller", False)),
                              "source": pr.get("source", "")})
    except Exception:
        feats = []
    _features = feats
    return list(_features)


def reload() -> int:
    """Drop the cache and re-read the file (e.g. after the builder regenerates it)."""
    global _points, _features
    _points = None
    _features = None
    return len(_load())


def count() -> int:
    return len(_load())


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


def signals_on_path_local(path):
    """Local mirror of live_signals.signals_on_path: every dataset signal within
    MAX_OFFSET_M of the route, nearest-first, tagged with distance-along-route,
    de-duplicated within MERGE_M. path = [(lat,lng), ...]. Returns [] if the
    dataset is empty/missing or the path is degenerate — never raises."""
    pts = _load()
    if not pts or len(path) < 2:
        return []
    try:
        cum = _cumulative(path)
        found = []
        for p in pts:
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
    except Exception:
        return []
