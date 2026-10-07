from __future__ import annotations
"""
Dispatch brain (standalone CAD core) — the layer ABOVE the safety engine.

It decides WHO responds: it holds a live fleet, creates incidents, and assigns
the nearest available unit. The engine/signal layer below only EXECUTES safely.

Incident-bound preemption (the H3 fix): a corridor is authorized only for a unit
that has an ASSIGNED/ACTIVE incident. A bare driver SOS earns nothing — you must
be dispatched. `is_preempt_authorized()` is the gate the coordinator consults
before it arms any signal.

Ambulance-first: units carry a class (code_red/code_blue now; fire_* later via
fire.register()). Nothing here is fire-specific.
"""
import itertools
import math
import time
from dataclasses import dataclass
from enum import Enum


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class UnitStatus(str, Enum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    ENROUTE = "enroute"
    ON_SCENE = "on_scene"
    TRANSPORTING = "transporting"
    OOS = "out_of_service"


class IncidentStatus(str, Enum):
    OPEN = "open"          # reported, not yet assigned
    ASSIGNED = "assigned"  # unit assigned, en route
    ACTIVE = "active"      # on scene / transporting
    CLOSED = "closed"


@dataclass
class Unit:
    id: str
    kind: str = "ambulance"          # ambulance | fire (later)
    cls: str = "code_red"            # priority class for the arbiter
    lat: float = 0.0
    lng: float = 0.0
    status: UnitStatus = UnitStatus.AVAILABLE
    incident_id: str | None = None
    last_seen: float = 0.0


@dataclass
class Incident:
    id: str
    lat: float
    lng: float
    type: str = "medical"            # medical | road_accident | fire ...
    priority: str = "code_red"
    status: IncidentStatus = IncidentStatus.OPEN
    unit_id: str | None = None
    dest_lat: float | None = None    # hospital, set when the transport leg begins
    dest_lng: float | None = None
    dest_name: str | None = None
    reported_via: str = "unknown"    # call | whatsapp | app ...
    address: str = ""                # raw address string (phone-call intake)
    note: str = ""
    created_at: float = 0.0


class Dispatcher:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.units: dict[str, Unit] = {}
        self.incidents: dict[str, Incident] = {}
        self._seq = itertools.count(1)

    # ---- fleet ----
    def register_unit(self, unit: Unit) -> None:
        unit.last_seen = self.clock()
        self.units[unit.id] = unit

    def update_unit(self, uid: str, lat=None, lng=None, status: UnitStatus | None = None) -> None:
        u = self.units.get(uid)
        if not u:
            return
        if lat is not None:
            u.lat = float(lat)
        if lng is not None:
            u.lng = float(lng)
        if status is not None:
            u.status = status
        u.last_seen = self.clock()

    # ---- incidents ----
    def create_incident(self, lat: float, lng: float, type: str = "medical",
                         priority: str = "code_red", reported_via: str = "unknown",
                         note: str = "") -> Incident:
        iid = f"INC-{next(self._seq):04d}"
        inc = Incident(id=iid, lat=float(lat), lng=float(lng), type=type,
                       priority=priority, reported_via=reported_via, note=note,
                       created_at=self.clock())
        self.incidents[iid] = inc
        return inc

    def nearest_available(self, lat: float, lng: float, kind: str = "ambulance") -> Unit | None:
        cands = [u for u in self.units.values()
                 if u.kind == kind and u.status == UnitStatus.AVAILABLE]
        if not cands:
            return None
        # straight-line proxy now; swap in a drive-time matrix (OSRM/Maps) later
        return min(cands, key=lambda u: haversine_m(lat, lng, u.lat, u.lng))

    def _bind(self, inc: "Incident", u: "Unit") -> "Unit":
        u.status = UnitStatus.ASSIGNED
        u.incident_id = inc.id
        u.cls = inc.priority
        inc.status = IncidentStatus.ASSIGNED
        inc.unit_id = u.id
        return u

    def assign(self, incident_id: str) -> Unit | None:
        inc = self.incidents.get(incident_id)
        if not inc or inc.status != IncidentStatus.OPEN:
            return None
        u = self.nearest_available(inc.lat, inc.lng)
        return self._bind(inc, u) if u else None

    def assign_unit(self, incident_id: str, unit_id: str) -> Unit | None:
        """Explicitly bind a specific unit to an incident (manual dispatch)."""
        inc = self.incidents.get(incident_id)
        u = self.units.get(unit_id)
        if not inc or not u or u.status != UnitStatus.AVAILABLE:
            return None
        return self._bind(inc, u)

    def set_destination(self, incident_id: str, lat: float, lng: float, name: str = "") -> None:
        inc = self.incidents.get(incident_id)
        if inc:
            inc.dest_lat, inc.dest_lng, inc.dest_name = float(lat), float(lng), name
            inc.status = IncidentStatus.ACTIVE

    def close_incident(self, incident_id: str) -> None:
        inc = self.incidents.get(incident_id)
        if not inc:
            return
        inc.status = IncidentStatus.CLOSED
        if inc.unit_id and inc.unit_id in self.units:
            u = self.units[inc.unit_id]
            u.status = UnitStatus.AVAILABLE
            u.incident_id = None

    # ---- the preemption gate (incident-bound SOS) ----
    def is_preempt_authorized(self, unit_id: str) -> bool:
        u = self.units.get(unit_id)
        if not u or u.incident_id is None:
            return False
        inc = self.incidents.get(u.incident_id)
        return bool(inc and inc.status in (IncidentStatus.ASSIGNED, IncidentStatus.ACTIVE))
