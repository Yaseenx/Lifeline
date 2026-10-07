from __future__ import annotations
"""Load config.yaml into plain objects. The corridor is data, not code."""
import math
import pathlib
from dataclasses import dataclass, field

import yaml


@dataclass
class JunctionCfg:
    id: str
    name: str
    lat: float
    lng: float
    corridor_dir: str  # 'NS' | 'EW'


@dataclass
class Timings:
    green_s: float
    amber_s: float
    allred_s: float
    min_green_s: float
    max_hold_s: float
    lead_m: float
    pass_m: float
    lease_ttl_ms: int
    tick_ms: int


@dataclass
class Config:
    junctions: list[JunctionCfg] = field(default_factory=list)
    timings: Timings = None  # type: ignore[assignment]
    freshness_window_s: float = 5.0
    devices: dict[str, str] = field(default_factory=dict)


def load(path: str | pathlib.Path | None = None) -> Config:
    p = pathlib.Path(path) if path else pathlib.Path(__file__).with_name("config.yaml")
    raw = yaml.safe_load(p.read_text())
    cfg = Config()
    for j in raw["corridor"]["junctions"]:
        cfg.junctions.append(JunctionCfg(**j))
    cfg.timings = Timings(**raw["timings"])
    sec = raw.get("security", {})
    cfg.freshness_window_s = float(sec.get("freshness_window_s", 5.0))
    cfg.devices = dict(sec.get("devices", {}))
    return cfg


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
