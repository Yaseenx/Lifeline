"""End-to-end: a WhatsApp bystander report becomes a dispatched unit whose whole
route is cleared in order, ahead of arrival — then the incident closes and the
corridor authorization drops. Ties intake -> dispatch -> route coordinator."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "server"))

import intake
from dispatch import Dispatcher, Unit
from coordinator import RouteCoordinator, RoutePlan, RouteStop


class Clk:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def test_e2e_whatsapp_to_corridor():
    d = Dispatcher(clock=Clk())
    d.register_unit(Unit(id="AMB-A", lat=13.10, lng=80.30))
    d.register_unit(Unit(id="AMB-B", lat=13.081, lng=80.276))   # nearest to MMC
    d.register_unit(Unit(id="AMB-C", lat=13.05, lng=80.20))

    # 1) bystander shares live location on WhatsApp
    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"location": {"latitude": 13.0809, "longitude": 80.2757},
         "text": {"body": "bike accident, bleeding"}}]}}]}]}
    loc = intake.parse_whatsapp_location(payload)
    res = intake.handle_report(d, loc["lat"], loc["lng"], loc["text"])
    assert res.accepted and res.unit.id == "AMB-B"

    # 2) route-aware coordinator, gated on dispatch authorization
    co = RouteCoordinator(arm_lead_s=20.0, authorizer=d.is_preempt_authorized)
    co.set_route(RoutePlan(unit_id=res.unit.id, incident_id=res.incident.id,
                           cls=res.incident.priority,
                           stops=[RouteStop("J1"), RouteStop("J2"), RouteStop("J3")]))
    p = [300.0, 700.0, 1100.0]; speed = 12.0; x = 0.0; armed = []
    while x <= 1300.0:
        etas = {jid: ((pk - x) / speed if pk > x else 0.0, abs(pk - x))
                for jid, pk in zip(("J1", "J2", "J3"), p)}
        for a in co.update(res.unit.id, etas):
            if a[0] == "arm":
                armed.append(a[1])
        x += 12.0
    assert armed == ["J1", "J2", "J3"]

    # 3) incident closes -> unit freed -> no further corridor
    d.close_incident(res.incident.id)
    assert not d.is_preempt_authorized(res.unit.id)
