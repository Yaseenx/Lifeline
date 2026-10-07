"""Corridor behavior on the REAL dispatch-driven engine: incident-bound
preemption (undispatched units get nothing), Red>Blue override, comms-loss TTL
revert, monitor fault scoping, epoch fencing, and a dispatched end-to-end run."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "server"))

import topology
from engine import Engine
from topology import haversine_m


class Clk:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def make():
    clk = Clk()
    return Engine(topology.load(), clock=clk), clk


def drive(e, clk, seconds):
    for _ in range(int(seconds * 10)):
        e.tick(0.1); clk.t += 0.1


def register(e, uid, j, off=0.003):
    """Stream telemetry -> engine auto-registers the unit as AVAILABLE."""
    e.telemetry({"device_id": uid, "lat": j.lat, "lng": j.lng + off,
                 "speed_kph": 30, "sos": True, "trip_id": uid})


def dispatch(e, uid, cls, j):
    """Create an incident and bind this specific unit -> authorizes preemption."""
    inc = e.dispatcher.create_incident(j.lat, j.lng, priority=cls, reported_via="call")
    return e.dispatcher.assign_unit(inc.id, uid)


def approach(e, clk, uid, j, start=0.004, step=0.0002, ticks=30, keepalive=()):
    lng = start
    for _ in range(ticks):
        lng -= step
        e.telemetry({"device_id": uid, "lat": j.lat, "lng": j.lng + lng,
                     "speed_kph": 30, "sos": True, "trip_id": uid})
        for other, off in keepalive:
            e.telemetry({"device_id": other, "lat": j.lat, "lng": j.lng + off,
                         "speed_kph": 0, "sos": True, "trip_id": other})
        drive(e, clk, 0.5)


def test_undispatched_unit_gets_no_corridor():
    e, clk = make()
    j = e.cfg.junctions[0]
    register(e, "IDLE-1", j)                 # available, NOT dispatched
    approach(e, clk, "IDLE-1", j, start=0.003, ticks=20)
    assert e.arbiters[j.id].state_for("IDLE-1") == "none"
    assert e.fsms[j.id].lease is None


def test_red_overrides_blue_then_blue_regranted():
    e, clk = make()
    j = e.cfg.junctions[0]
    register(e, "BLUE-1", j, 0.003); dispatch(e, "BLUE-1", "code_blue", j)
    approach(e, clk, "BLUE-1", j, start=0.003, ticks=12)
    assert e.arbiters[j.id].state_for("BLUE-1") == "owner"
    register(e, "RED-1", j, 0.003); dispatch(e, "RED-1", "code_red", j)
    blue_lng = 0.003 - 0.0002 * 12
    approach(e, clk, "RED-1", j, start=0.003, ticks=12, keepalive=[("BLUE-1", blue_lng)])
    assert e.arbiters[j.id].state_for("RED-1") == "owner"
    assert e.arbiters[j.id].state_for("BLUE-1") == "queued"
    e.sos({"device_id": "RED-1", "active": False})     # red ends trip -> deauthorized
    for _ in range(4):
        e.telemetry({"device_id": "BLUE-1", "lat": j.lat, "lng": j.lng + blue_lng,
                     "speed_kph": 0, "sos": True, "trip_id": "BLUE-1"})
        drive(e, clk, 0.5)
    assert e.arbiters[j.id].state_for("BLUE-1") == "owner"


def test_comms_loss_reverts_via_ttl():
    e, clk = make()
    j = e.cfg.junctions[0]
    register(e, "AMB-9", j, 0.003); dispatch(e, "AMB-9", "code_red", j)
    approach(e, clk, "AMB-9", j, start=0.003, ticks=12)
    fsm = e.fsms[j.id]
    assert fsm.lease and fsm.lease.owner == "AMB-9"
    e.online = False
    drive(e, clk, 4)
    assert fsm.lease is None, "lease survived comms loss"
    assert fsm.mode in ("NORMAL", "EXIT_CLEAR")
    assert not e.monitors[j.id].latched


def test_monitor_fault_scoped_and_blocks_grants():
    e, clk = make()
    j1, j2 = e.cfg.junctions[0], e.cfg.junctions[1]
    e.monitors[j2.id].trip("forced (drill)")
    register(e, "AMB-2", j2, 0.003); dispatch(e, "AMB-2", "code_red", j2)
    approach(e, clk, "AMB-2", j2, start=0.003, ticks=12)
    assert e.arbiters[j2.id].state_for("AMB-2") == "none"
    assert e.node_state(j2.id, "AMB-2") == "rejected"
    assert not e.monitors[j1.id].latched
    snap = e.snapshot()
    lamps2 = next(x["lamps"] for x in snap["junctions"] if x["id"] == j2.id)
    assert lamps2 == {"ns": "flash", "ew": "flash"}
    e.monitors[j2.id].external_reset()
    assert not e.monitors[j2.id].latched


def test_stale_epoch_rejected_by_fsm():
    e, clk = make()
    fsm = e.fsms[e.cfg.junctions[0].id]
    assert fsm.request_preempt("A", 5, clk(), 1.5) in ("entering", "granted")
    fsm.release("A")
    assert fsm.request_preempt("B", 7, clk(), 1.5) in ("entering", "granted")
    assert fsm.request_preempt("C", 6, clk(), 1.5) == "rejected"


def test_dispatched_corridor_end_to_end():
    e, clk = make()
    js = e.cfg.junctions
    start = (js[0].lat, js[0].lng + 0.006)
    e.telemetry({"device_id": "AMB-1", "lat": start[0], "lng": start[1],
                 "speed_kph": 30, "sos": True, "trip_id": "AMB-1"})
    inc = e.dispatcher.create_incident(start[0], start[1], priority="code_red", reported_via="call")
    e.dispatcher.assign_unit(inc.id, "AMB-1")
    path = [start] + [(j.lat, j.lng) for j in js] + [(js[-1].lat, js[-1].lng - 0.004)]
    granted, passed = set(), set()
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        steps = max(2, int(haversine_m(a[0], a[1], b[0], b[1]) / 6.0))  # ~6 m/step
        for s in range(steps + 1):
            f = s / steps
            lat = a[0] + (b[0] - a[0]) * f
            lng = a[1] + (b[1] - a[1]) * f
            e.telemetry({"device_id": "AMB-1", "lat": lat, "lng": lng,
                         "speed_kph": 30, "sos": True, "trip_id": "AMB-1"})
            drive(e, clk, 0.5)
            for j in js:
                if e.node_state(j.id, "AMB-1") == "granted":
                    granted.add(j.id)
                if e.ambulances["AMB-1"].passed.get(j.id):
                    passed.add(j.id)
    assert {"J1", "J2", "J3"} <= granted, granted
    assert {"J1", "J2", "J3"} <= passed, passed
    assert all(f.lease is None for f in e.fsms.values())
    assert all(not m.latched for m in e.monitors.values())


def test_gps_plausibility_rejects_teleport():
    e, clk = make()
    j = e.cfg.junctions[0]
    e.telemetry({"device_id": "AMB-1", "lat": j.lat, "lng": j.lng + 0.01, "speed_kph": 30, "sos": True})
    clk.t += 1.0
    p0 = (e.ambulances["AMB-1"].lat, e.ambulances["AMB-1"].lng)
    # ~150 km jump in 1 s -> rejected, position unchanged
    e.telemetry({"device_id": "AMB-1", "lat": j.lat + 1.0, "lng": j.lng + 1.0, "speed_kph": 30, "sos": True})
    assert (e.ambulances["AMB-1"].lat, e.ambulances["AMB-1"].lng) == p0, "teleport not rejected"
    clk.t += 1.0
    # a normal small move IS accepted
    e.telemetry({"device_id": "AMB-1", "lat": j.lat, "lng": j.lng + 0.0099, "speed_kph": 30, "sos": True})
    assert e.ambulances["AMB-1"].lng != p0[1], "legit fix wrongly rejected"
