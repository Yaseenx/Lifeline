"""Route-derived dynamic corridor on the real engine: signals on a unit's route
become virtual junctions that preempt in a green wave, dedupe to configured
controllers, and tear down when the trip ends. Configured junctions still work
with no route set (backward compatible)."""
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "server"))

import topology
from engine import Engine


class Clk:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def make():
    clk = Clk()
    return Engine(topology.load(), clock=clk), clk


def dispatch(e, uid, dlat, dlng):
    inc = e.dispatcher.create_incident(dlat, dlng, priority="code_red", reported_via="call")
    e.dispatcher.assign_unit(inc.id, uid)


def tele(e, uid, lat, lng):
    e.telemetry({"device_id": uid, "lat": lat, "lng": lng, "speed_kph": 40, "sos": True, "fix": True})


def drive(e, uid, clk, lng_from, lng_to, lat, step=0.0001, rec=None):
    lng = lng_from
    while lng > lng_to:
        lng -= step
        tele(e, uid, lat, lng)
        for _ in range(10):
            e.tick(0.1); clk.t += 0.1
        if rec is not None:
            for jid in list(e.junctions):
                if e.node_state(jid, uid) == "granted":
                    rec["granted"].add(jid)
                if e.ambulances[uid].passed.get(jid):
                    rec["passed"].add(jid)


def test_route_derived_corridor_green_wave_and_teardown():
    e, clk = make()
    j1 = next(j for j in e.junctions.values() if j.id == "J1")   # a configured controller
    lat = j1.lat
    base = len(e.junctions)
    tele(e, "AMB", lat, j1.lng + 0.0044)                          # east of J1
    dispatch(e, "AMB", lat, j1.lng - 0.0040)
    # signals on the route: two new + one AT J1 (dedupe to the controller)
    signals = [{"lat": lat, "lng": j1.lng + 0.0024},
               {"lat": lat, "lng": j1.lng},                       # == J1 -> dedupe
               {"lat": lat, "lng": j1.lng - 0.0016}]
    e.set_route("AMB", signals, path=[{"lat": lat, "lng": j1.lng + 0.004},
                                      {"lat": lat, "lng": j1.lng - 0.004}])
    order = e._unit_routes["AMB"]["order"]
    assert "J1" in order                                          # deduped to the controller
    assert len(e.junctions) == base + 2                           # two new virtual junctions
    assert sum(1 for x in e.junctions.values() if x.virtual) == 2

    rec = {"granted": set(), "passed": set()}
    drive(e, "AMB", clk, j1.lng + 0.0039, j1.lng - 0.0021, lat, rec=rec)
    for jid in order:
        assert jid in rec["granted"], (jid, rec["granted"])       # each cleared (green wave)
        assert jid in rec["passed"], (jid, rec["passed"])
    assert all(not m.latched for m in e.monitors.values())        # no safety fault

    c = e.corridor_for("AMB")
    assert [n["id"] for n in c["nodes"]] == order
    assert any(n["controlled"] for n in c["nodes"]) and any(not n["controlled"] for n in c["nodes"])

    e.clear_route("AMB")                                          # trip over
    assert len(e.junctions) == base                               # virtual junctions pruned
    assert sum(1 for x in e.junctions.values() if x.virtual) == 0


def test_no_route_still_preempts_configured_junction():
    e, clk = make()
    j1 = next(j for j in e.junctions.values() if j.id == "J1")
    lat = j1.lat
    tele(e, "AMB", lat, j1.lng + 0.0044)
    dispatch(e, "AMB", lat, j1.lng - 0.0010)
    rec = {"granted": set(), "passed": set()}
    drive(e, "AMB", clk, j1.lng + 0.0039, j1.lng - 0.0011, lat, rec=rec)   # NO set_route
    assert "J1" in rec["granted"] and "J1" in rec["passed"], rec
    assert all(not m.latched for m in e.monitors.values())
