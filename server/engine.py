from __future__ import annotations
"""Authoritative 10 Hz engine: telemetry -> (dispatch authorization) -> arbiter
-> FSMs -> monitor.

Preemption is INCIDENT-BOUND: a unit gets a corridor only while it is dispatched
to an active incident (dispatch.is_preempt_authorized). A bare SOS or an
available ambulance driving past earns nothing.

Junctions are DYNAMIC and route-derived. Configured junctions are the designated
CONTROLLER sites (real hardware to be fitted). As a dispatched unit gets a route,
the signals on that route are added as VIRTUAL junctions (simulated) via
set_route(); each runs the identical FSM + monitor + arbiter machinery so the
green wave is faithful. A junction with `controlled=True` is (or will be) driven
by a real signal controller at the edge; virtual ones are simulation only until a
controller is installed there. Different route -> different junctions.

Each pipeline layer can only REDUCE authority:
  1. ingest telemetry (already authenticated at the gateway) + register unit
  2. per authorized unit x junction: proximity/approach gating -> arbiter
  3. arbiter owner -> FSM preempt/renew (lease TTL = fail-safe)
  4. FSM tick through mandatory safe intervals
  5. INDEPENDENT monitor observes commanded lamps; latched -> flash-red
"""
import time
from dataclasses import dataclass, field

import intake
from arbiter import JunctionArbiter
from controller import JunctionFSM
from dispatch import Dispatcher, IncidentStatus, Unit, UnitStatus
from monitor import SafetyMonitor
from topology import Config, haversine_m

STALE_TELEMETRY_S = 5.0
ETA_FLOOR_MPS = 3.0


def _project(p, a, b):
    import math
    k = math.cos(math.radians(a[0]))
    bx = (b[1] - a[1]) * k; by = b[0] - a[0]
    px = (p[1] - a[1]) * k; py = p[0] - a[0]
    l2 = bx * bx + by * by or 1e-12
    t = max(0.0, min(1.0, (px * bx + py * by) / l2))
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def _route_remaining_m(path, lat, lng):
    """Remaining distance (m) along a road route to its end, measured from the point
    on the route nearest to (lat,lng). The single, server-authoritative basis for the
    destination ETA — both the ambulance dashboard and the hospital console display it."""
    pts = [(q.get("lat"), q.get("lng")) for q in (path or []) if isinstance(q, dict)]
    pts = [q for q in pts if q[0] is not None and q[1] is not None]
    if len(pts) < 2:
        return None
    cum = [0.0]
    for i in range(1, len(pts)):
        cum.append(cum[-1] + haversine_m(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]))
    total = cum[-1]
    best, along = 1e18, 0.0
    for i in range(len(pts) - 1):
        s = _project((lat, lng), pts[i], pts[i + 1])
        d = haversine_m(lat, lng, s[0], s[1])
        if d < best:
            best = d
            along = cum[i] + haversine_m(pts[i][0], pts[i][1], s[0], s[1])
    return max(0.0, total - along)
MAX_PLAUSIBLE_MPS = 60.0  # ~216 km/h between consecutive fixes = teleport/spoof
DEDUPE_JUNCTION_M = 55.0  # a route signal this close to an existing junction = same junction
MAX_ROUTE_SIGNALS = 60    # cap virtual junctions per route (request-flood guard)


@dataclass
class Ambulance:
    id: str
    lat: float = 0.0
    lng: float = 0.0
    speed_mps: float = 0.0
    cls: str = "code_red"
    sos: bool = False
    sos_ts: float = 0.0
    trip_id: str | None = None
    trip_type: str = "SCENE"
    leg: int = 2
    dest_id: str | None = None
    dest_name: str | None = None
    dest_lat: float | None = None
    dest_lng: float | None = None
    scene_lat: float | None = None   # leg-1 target: the accident / pickup location
    scene_lng: float | None = None
    last_seen: float = 0.0
    prev_dist: dict = field(default_factory=dict)
    approaching: dict = field(default_factory=dict)
    receding: dict = field(default_factory=dict)
    passed: dict = field(default_factory=dict)
    has_fix: bool = False


@dataclass
class Junction:
    """A signal the engine manages. Configured junctions are the designated
    CONTROLLER sites (controlled=True). Route-derived ones are VIRTUAL
    (simulated) until a controller is installed there."""
    id: str
    name: str
    lat: float
    lng: float
    corridor_dir: str = "EW"
    controlled: bool = False  # a real signal controller is/will be installed here
    virtual: bool = False     # route-derived (simulated), not a configured site


class Engine:
    def __init__(self, cfg: Config, clock=time.monotonic):
        self.cfg = cfg
        self.clock = clock
        self.junctions: dict[str, Junction] = {}
        self.fsms: dict[str, JunctionFSM] = {}
        self.monitors: dict[str, SafetyMonitor] = {}
        self.arbiters: dict[str, JunctionArbiter] = {}
        for j in cfg.junctions:  # configured junctions = designated controller sites
            self._ensure_junction(Junction(id=j.id, name=j.name, lat=j.lat, lng=j.lng,
                                            corridor_dir=j.corridor_dir, controlled=True, virtual=False))
        self.dispatcher = Dispatcher(clock=clock)
        self.ambulances: dict[str, Ambulance] = {}
        self._unit_routes: dict[str, dict] = {}  # unit_id -> {order:[jid], path:[{lat,lng}], updated}
        self.log: list[dict] = []
        self.tick_n = 0
        self.online = True   # ops kill-switch: False = stop renewals/grants

    # ---------- dynamic junction lifecycle ----------
    def _ensure_junction(self, j: "Junction") -> None:
        if j.id in self.junctions:
            return
        t = self.cfg.timings
        self.junctions[j.id] = j
        self.fsms[j.id] = JunctionFSM(j.id, t.green_s, t.amber_s, t.allred_s,
                                      t.min_green_s, t.max_hold_s, j.corridor_dir)
        self.monitors[j.id] = SafetyMonitor(j.id, t.amber_s, t.allred_s, t.min_green_s)
        self.arbiters[j.id] = JunctionArbiter(j.id)

    def _drop_junction(self, jid: str) -> None:
        j = self.junctions.get(jid)
        if not j or not j.virtual:
            return  # never drop a configured controller site
        for a in self.ambulances.values():
            if jid in self.arbiters and self.arbiters[jid].state_for(a.id) != "none":
                self._handoff(jid, a.id, "route_changed")
            a.prev_dist.pop(jid, None); a.approaching.pop(jid, None)
            a.receding.pop(jid, None); a.passed.pop(jid, None)
        self.fsms.pop(jid, None); self.monitors.pop(jid, None)
        self.arbiters.pop(jid, None); self.junctions.pop(jid, None)

    @staticmethod
    def _sig_id(lat: float, lng: float) -> str:
        return f"SIG-{lat:.5f},{lng:.5f}"

    def set_route(self, unit_id: str, signals: list[dict], path: list | None = None) -> None:
        """Build the unit's corridor from the signals on its route: each becomes a
        virtual junction (deduped against existing junctions), the unit's ordered
        junction list is recorded, and virtual junctions no route uses are pruned.
        `signals` = [{lat,lng,name?}] nearest-first (from live_signals)."""
        order: list[str] = []
        for i, s in enumerate(signals[:MAX_ROUTE_SIGNALS]):
            try:
                lat, lng = float(s["lat"]), float(s["lng"])
            except (KeyError, TypeError, ValueError):
                continue
            match = next((jid for jid, j in self.junctions.items()
                          if haversine_m(lat, lng, j.lat, j.lng) <= DEDUPE_JUNCTION_M), None)
            if match:
                if match not in order:
                    order.append(match)
                continue
            jid = self._sig_id(lat, lng)
            self._ensure_junction(Junction(id=jid, name=s.get("name") or f"Signal {i + 1}",
                                           lat=lat, lng=lng, corridor_dir="EW",
                                           controlled=False, virtual=True))
            if jid not in order:
                order.append(jid)
        self._unit_routes[unit_id] = {"order": order, "path": list(path or []), "updated": self.clock()}
        self._prune_virtual()

    def clear_route(self, unit_id: str) -> None:
        if self._unit_routes.pop(unit_id, None) is not None:
            self._prune_virtual()

    def _prune_virtual(self) -> None:
        used: set[str] = set()
        for r in self._unit_routes.values():
            used.update(r["order"])
        for jid, j in list(self.junctions.items()):
            if j.virtual and jid not in used:
                self._drop_junction(jid)

    # ---------- authorization helpers (incident-bound preemption) ----------
    def _managed(self, amb_id: str) -> bool:
        return amb_id in self.dispatcher.units

    def _active(self, a: "Ambulance") -> bool:
        if self._managed(a.id):
            return self.dispatcher.is_preempt_authorized(a.id)
        return a.sos

    def _prio(self, a: "Ambulance") -> tuple:
        if self._managed(a.id):
            u = self.dispatcher.units[a.id]
            inc = self.dispatcher.incidents.get(u.incident_id or "")
            if inc:
                return u.cls, inc.created_at
        return a.cls, a.sos_ts

    def _plausible(self, a: "Ambulance", lat: float, lng: float, now: float) -> bool:
        if not a.has_fix:
            return True
        dt = now - a.last_seen
        if dt <= 0 or dt > STALE_TELEMETRY_S:
            return True
        return haversine_m(a.lat, a.lng, lat, lng) / dt <= MAX_PLAUSIBLE_MPS

    def _ensure_self_dispatch(self, a: "Ambulance") -> None:
        """Crew-initiated emergency with no control-centre incident: open a
        self-dispatched incident bound to this unit so it still earns the
        corridor. No-op if already assigned (console/WhatsApp or self)."""
        disp = self.dispatcher
        if a.id not in disp.units:
            disp.register_unit(Unit(id=a.id, lat=a.lat, lng=a.lng, cls=a.cls))
        u = disp.units[a.id]
        inc = disp.incidents.get(u.incident_id) if u.incident_id else None
        if inc and inc.status != IncidentStatus.CLOSED:
            return
        u.status = UnitStatus.AVAILABLE
        incident = disp.create_incident(lat=a.lat or 0.0, lng=a.lng or 0.0,
                                        type="crew_initiated", priority=a.cls,
                                        reported_via="unit", note="crew-initiated emergency")
        disp.assign_unit(incident.id, a.id)
        self._log("self_dispatch", a.id, "", incident.id)

    # ---------- ingestion (called by the gateway; already authenticated) ----------
    def telemetry(self, d: dict) -> None:
        if not self.online:
            return
        uid = d["device_id"]
        a = self.ambulances.setdefault(uid, Ambulance(id=uid))
        now = self.clock()
        lat, lng = float(d.get("lat", 0)), float(d.get("lng", 0))
        # A frame carries a position only if the vehicle actually has a GPS fix.
        # No fix (or the 0,0 null-island default) must NEVER be stored.
        has_pos = bool(d.get("fix", True)) and not (abs(lat) < 1e-6 and abs(lng) < 1e-6)
        if has_pos and not self._plausible(a, lat, lng, now):
            self._log("gps_reject", uid, "", "implausible fix (teleport/speed)")
            has_pos = False
        if has_pos:
            a.lat, a.lng = lat, lng
            a.has_fix = True
            a.speed_mps = float(d.get("speed_kph", 0)) / 3.6
        else:
            a.speed_mps = 0.0
        a.trip_id = d.get("trip_id")
        sos = bool(d.get("sos"))
        if sos and not a.sos:
            a.sos_ts = now
            a.passed = {}
        a.sos = sos
        a.last_seen = now
        # register / update the unit in the dispatcher (available until assigned)
        if uid not in self.dispatcher.units:
            self.dispatcher.register_unit(Unit(id=uid, lat=a.lat, lng=a.lng))
        else:
            self.dispatcher.update_unit(uid, lat=a.lat, lng=a.lng)
        if a.has_fix:
            self._motion_update(a)

    def _motion_update(self, a: "Ambulance") -> None:
        for j in list(self.junctions.values()):
            d = haversine_m(a.lat, a.lng, j.lat, j.lng)
            prev = a.prev_dist.get(j.id)
            if prev is None:
                a.approaching[j.id] = True
                a.receding[j.id] = False
                a.prev_dist[j.id] = d
            elif d < prev - 1.0:
                a.approaching[j.id] = True
                a.receding[j.id] = False
                a.prev_dist[j.id] = d
            elif d > prev + 1.0:
                a.approaching[j.id] = False
                a.receding[j.id] = True
                a.prev_dist[j.id] = d

    def sos(self, d: dict) -> None:
        if not self.online:
            return
        uid = d["device_id"]
        a = self.ambulances.setdefault(uid, Ambulance(id=uid))
        active = bool(d.get("active"))
        if active and not a.sos:
            a.sos_ts = self.clock()
            a.passed = {}
        a.sos = active
        a.cls = d.get("condition") or a.cls
        a.trip_id = d.get("trip_id") or a.trip_id
        a.last_seen = self.clock()
        if active:
            # crew raised an emergency: self-dispatch if no incident owns it yet
            self._ensure_self_dispatch(a)
        else:
            self._release_everywhere(a.id, "sos_off")
            self.clear_route(a.id)  # trip over -> tear down its dynamic corridor
            u = self.dispatcher.units.get(a.id)
            if u and u.incident_id:
                self.dispatcher.close_incident(u.incident_id)

    def trip(self, d: dict) -> None:
        uid = d["device_id"]
        a = self.ambulances.setdefault(uid, Ambulance(id=uid))
        if d.get("condition"):
            a.cls = d["condition"]
        if d.get("trip_type"):
            a.trip_type = d["trip_type"]
        if d.get("leg"):
            a.leg = int(d["leg"])
        if d.get("destination_id") is not None:
            a.dest_id = d.get("destination_id")
        dest = d.get("destination") or {}
        if d.get("destination_name") or dest.get("name"):
            a.dest_name = d.get("destination_name") or dest.get("name")
        lat = d.get("destination_lat", dest.get("lat"))
        lng = d.get("destination_lng", dest.get("lng"))
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            a.dest_lat, a.dest_lng = float(lat), float(lng)
        # leg-1 target: the accident / pickup location the crew responds to first
        origin = d.get("origin") or {}
        olat, olng = origin.get("lat"), origin.get("lng")
        a.scene_lat = float(olat) if isinstance(olat, (int, float)) else None
        a.scene_lng = float(olng) if isinstance(olng, (int, float)) else None
        a.last_seen = self.clock()

    # ---------- intake -> dispatch (the real trigger) ----------
    async def dispatch_call(self, address: str, text: str = "",
                            incident_type: str | None = None, priority: str | None = None):
        return await intake.report_from_address(self.dispatcher, address, text=text,
                                                via="call", incident_type=incident_type,
                                                priority=priority)

    def dispatch_whatsapp(self, lat: float, lng: float, text: str = ""):
        return intake.handle_report(self.dispatcher, lat, lng, text=text, via="whatsapp")

    def close_incident(self, incident_id: str) -> None:
        inc = self.dispatcher.incidents.get(incident_id)
        unit_id = inc.unit_id if inc else None
        self.dispatcher.close_incident(incident_id)
        if unit_id:
            self.clear_route(unit_id)

    # ---------- the tick ----------
    def tick(self, dt: float) -> None:
        now = self.clock()
        self.tick_n += 1
        t = self.cfg.timings
        for a in list(self.ambulances.values()):
            stale = (now - a.last_seen) > STALE_TELEMETRY_S
            active = self._active(a)
            cls, ts = self._prio(a)
            for j in list(self.junctions.values()):
                fsm, arb, mon = self.fsms[j.id], self.arbiters[j.id], self.monitors[j.id]
                d = haversine_m(a.lat, a.lng, j.lat, j.lng)
                approaching = a.approaching.get(j.id, True)
                receding = a.receding.get(j.id, False)
                if a.passed.get(j.id):
                    continue
                if receding and d < t.pass_m:
                    a.passed[j.id] = True
                    if arb.state_for(a.id) == "owner":
                        self._handoff(j.id, a.id, "passed")
                    continue
                want = (self.online and active and not stale and not mon.latched
                        and d < t.lead_m and (approaching or d < t.pass_m * 2))
                st = arb.state_for(a.id)
                if want and st == "none":
                    if arb.request(a.id, cls, ts) == "owner":
                        fsm.request_preempt(a.id, arb.epoch, now, t.lease_ttl_ms / 1000)
                        self._log("grant_request", a.id, j.id, cls)
                elif want and st == "owner":
                    if fsm.lease is None or fsm.lease.owner != a.id:
                        fsm.request_preempt(a.id, arb.epoch, now, t.lease_ttl_ms / 1000)
                    fsm.renew(a.id, now, t.lease_ttl_ms / 1000)
                elif not want and st != "none":
                    if st == "owner":
                        self._handoff(j.id, a.id, "released")
                    else:
                        arb.release(a.id)

        for jid, fsm in list(self.fsms.items()):
            fsm.tick(dt, now)
            for kind, detail in fsm.events:
                self._log(kind, str(detail), jid, "")
            if jid in self.monitors:
                self.monitors[jid].observe(fsm.lamps(), dt, now)

    # ---------- helpers ----------
    def _handoff(self, jid: str, amb_id: str, why: str) -> None:
        arb, fsm = self.arbiters[jid], self.fsms[jid]
        fsm.release(amb_id)
        nxt = arb.release(amb_id)
        self._log("release", amb_id, jid, why)
        if nxt:
            fsm.request_preempt(nxt.amb_id, arb.epoch, self.clock(),
                                self.cfg.timings.lease_ttl_ms / 1000)
            self._log("grant_request", nxt.amb_id, jid, nxt.cls)

    def _release_everywhere(self, amb_id: str, why: str) -> None:
        for jid in list(self.fsms):
            if self.arbiters[jid].state_for(amb_id) != "none":
                self._handoff(jid, amb_id, why)

    def _log(self, kind: str, who: str, jid: str, extra: str) -> None:
        self.log.append({"ts": round(self.clock(), 2), "kind": kind,
                         "who": who, "junction": jid, "extra": extra})
        del self.log[:-200]

    # ---------- views ----------
    def eta_green_s(self, jid: str) -> float | None:
        f = self.fsms[jid]
        t = self.cfg.timings
        if self.monitors[jid].latched:
            return None
        if f.mode == "HOLD":
            return 0.0
        if f.mode in ("ENTRY_WAIT", "ENTRY_CLEAR"):
            if f.phase == "GREEN":
                if f.active == f.desired:
                    return 0.0
                return max(0.0, t.min_green_s - f.phase_age) + t.amber_s + t.allred_s
            if f.phase == "AMBER":
                return max(0.0, t.amber_s - f.phase_age) + t.allred_s
            return max(0.0, t.allred_s - f.phase_age)
        return None

    def node_state(self, jid: str, amb_id: str) -> str:
        mon, fsm, arb = self.monitors[jid], self.fsms[jid], self.arbiters[jid]
        if mon.latched:
            return "rejected"
        st = arb.state_for(amb_id)
        if st == "owner":
            return "granted" if fsm.mode == "HOLD" and fsm.lease and fsm.lease.owner == amb_id else "requested"
        if st == "queued":
            return "queued"
        return "idle"

    def corridor_for(self, amb_id: str) -> dict | None:
        a = self.ambulances.get(amb_id)
        if not a or not a.has_fix or not self._active(a):
            return None  # no valid GPS fix / not authorized -> no corridor
        route = self._unit_routes.get(amb_id)
        jids = route["order"] if (route and route["order"]) else list(self.junctions.keys())
        nodes = []
        for jid in jids:
            j = self.junctions.get(jid)
            if not j:
                continue
            d = haversine_m(a.lat, a.lng, j.lat, j.lng)
            state = "passed" if a.passed.get(jid) else self.node_state(jid, amb_id)
            eta = round(d / max(a.speed_mps, ETA_FLOOR_MPS))
            green_in = self.eta_green_s(jid) if state in ("granted", "requested") else None
            nodes.append({"id": jid, "name": j.name, "lat": j.lat, "lng": j.lng,
                          "state": state, "eta_sec": eta,
                          "green_in_s": None if green_in is None else round(green_in, 1),
                          "controlled": j.controlled})
        qpos = 1
        for jid in jids:
            arb = self.arbiters.get(jid)
            if arb and arb.state_for(amb_id) == "queued":
                qpos = max(qpos, 2 + [q.amb_id for q in arb.queue].index(amb_id))
        dest_m = dest_eta = None
        # ETA to whatever the unit is currently driving to (scene on leg 1, hospital on
        # leg 2) = remaining along its road route. Straight-line only if no route yet.
        rem = _route_remaining_m(route["path"], a.lat, a.lng) if route and route.get("path") else None
        if rem is None and a.dest_lat is not None and a.dest_lng is not None:
            rem = haversine_m(a.lat, a.lng, a.dest_lat, a.dest_lng)
        if rem is not None:
            dest_m = round(rem)
            dest_eta = round(rem / max(a.speed_mps, ETA_FLOOR_MPS))
        return {"status": "active", "trip_id": a.trip_id, "queue_position": qpos,
                "safe_speed_kph": 38, "nodes": nodes,
                "path": route["path"] if route else [],
                "dest_distance_m": dest_m, "dest_eta_sec": dest_eta}

    def snapshot(self) -> dict:
        now = self.clock()
        juncs = []
        for j in self.junctions.values():
            f, mon, arb = self.fsms[j.id], self.monitors[j.id], self.arbiters[j.id]
            juncs.append({
                "id": j.id, "name": j.name, "lat": j.lat, "lng": j.lng,
                "corridor_dir": j.corridor_dir, "controlled": j.controlled, "virtual": j.virtual,
                "lamps": {"ns": "flash", "ew": "flash"} if mon.latched else f.lamps(),
                "mode": "FAULT" if mon.latched else f.mode,
                "owner": f.lease.owner if f.lease else None,
                "ttl_ms": max(0, round((f.lease.expires_at - now) * 1000)) if f.lease else None,
                "fault": mon.fault,
                "queue": [q.amb_id for q in arb.queue],
                "eta_green_s": (lambda v: None if v is None else round(v, 1))(self.eta_green_s(j.id)) if f.lease else None,
            })
        ambs = []
        for a in self.ambulances.values():
            active = self._active(a)
            engage = {}
            for jid in self.junctions:
                st = "passed" if a.passed.get(jid) else self.node_state(jid, a.id)
                if st != "idle" and active:
                    engage[jid] = st
            route = self._unit_routes.get(a.id)
            dest_m = dest_eta = None
            if active:
                rem = _route_remaining_m(route["path"], a.lat, a.lng) if route and route.get("path") else None
                if rem is None and a.dest_lat is not None and a.dest_lng is not None:
                    rem = haversine_m(a.lat, a.lng, a.dest_lat, a.dest_lng)
                if rem is not None:
                    dest_m = round(rem)
                    dest_eta = round(rem / max(a.speed_mps, ETA_FLOOR_MPS))
            ambs.append({
                "id": a.id, "lat": round(a.lat, 6), "lng": round(a.lng, 6),
                "has_fix": a.has_fix,
                "cls": a.cls, "sos": a.sos, "active": active,
                "speed_kph": round(a.speed_mps * 3.6, 1),
                "trip_id": a.trip_id, "trip_type": a.trip_type, "leg": a.leg,
                "dest": ({"id": a.dest_id, "name": a.dest_name,
                          "lat": a.dest_lat, "lng": a.dest_lng}
                         if (a.dest_name or a.dest_lat is not None) else None),
                # where the CURRENT leg is heading: the accident (leg 1) or the
                # hospital (leg 2). The route + ops marker follow this, not dest.
                "target": ({"kind": "scene", "lat": a.scene_lat, "lng": a.scene_lng, "name": "Accident scene"}
                           if (a.leg == 1 and a.scene_lat is not None and a.scene_lng is not None)
                           else ({"kind": "dest", "lat": a.dest_lat, "lng": a.dest_lng, "name": a.dest_name}
                                 if a.dest_lat is not None else None)),
                "route": route["path"] if (route and active) else None,
                "dest_distance_m": dest_m, "dest_eta_sec": dest_eta,
                "engage": engage,
                "stale": (now - a.last_seen) > STALE_TELEMETRY_S,
            })
        incidents = [{"id": i.id, "type": i.type, "priority": i.priority,
                      "status": i.status.value if hasattr(i.status, "value") else i.status,
                      "unit": i.unit_id, "via": i.reported_via,
                      "address": i.address, "lat": i.lat, "lng": i.lng}
                     for i in self.dispatcher.incidents.values()]
        return {"type": "state", "online": self.online, "tick": self.tick_n,
                "junctions": juncs, "ambulances": ambs, "incidents": incidents,
                "log": self.log[-40:]}
