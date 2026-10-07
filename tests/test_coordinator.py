"""Route-aware coordinator: arms every junction on the route in order, ahead of
arrival, releases after the unit passes, and arms nothing for an unauthorized
unit (incident-bound preemption)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "server"))

from coordinator import RouteCoordinator, RoutePlan, RouteStop
from dispatch import Dispatcher, Unit


def _plan(cls="code_red"):
    return RoutePlan(unit_id="AMB-B", incident_id="INC-0001", cls=cls,
                     stops=[RouteStop("J1"), RouteStop("J2"), RouteStop("J3")])


def test_arms_in_route_order_and_releases_after_pass():
    co = RouteCoordinator(arm_lead_s=20.0, pass_m=60.0)
    co.set_route(_plan())
    p = [300.0, 700.0, 1100.0]; speed = 12.0
    armed_order, released = [], set()
    x = 0.0
    while x <= 1300.0:
        etas = {jid: ((pk - x) / speed if pk > x else 0.0, abs(pk - x))
                for jid, pk in zip(("J1", "J2", "J3"), p)}
        for act in co.update("AMB-B", etas):
            if act[0] == "arm":
                armed_order.append(act[1])
            if act[0] == "release":
                released.add(act[1])
        x += 12.0
    assert armed_order == ["J1", "J2", "J3"], armed_order
    assert released == {"J1", "J2", "J3"}, released
    assert all(s.passed for s in co.plans["AMB-B"].stops)


def test_unauthorized_unit_gets_no_arms():
    d = Dispatcher()
    d.register_unit(Unit(id="AMB-B", lat=13.081, lng=80.276))   # no incident assigned
    co = RouteCoordinator(arm_lead_s=20.0, authorizer=d.is_preempt_authorized)
    co.set_route(_plan())
    acts = co.update("AMB-B", {"J1": (5.0, 60.0), "J2": (15.0, 180.0), "J3": (25.0, 300.0)})
    assert all(a[0] != "arm" for a in acts)
