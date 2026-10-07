from __future__ import annotations
"""
Route-aware corridor coordinator (RP2 + RP4).

Given the ORDERED junctions on a unit's route — each with a live ETA — it arms
each junction AHEAD of arrival (ETA look-ahead) so the signal is already green
when the unit gets there, then releases it once the unit has passed. This is
the difference between "clear a junction when the ambulance is within 450 m"
(today) and "know the whole route and clear every signal on it, in order,
before arrival" (the goal).

Output is a list of ACTIONS — ("arm", jid, cls, incident_id) / ("release", jid)
— that the caller relays to each junction's embedded signal module
(signal_node.IntelligentSignal) as authenticated priority requests. The
coordinator NEVER drives lamps; the signal disposes safely on its own.

It refuses to arm anything for a unit whose incident isn't dispatch-authorized
(incident-bound preemption).
"""
from dataclasses import dataclass, field


@dataclass
class RouteStop:
    jid: str
    eta_s: float = 1e9          # seconds to reach this junction (updated from GPS)
    dist_m: float = 1e9
    armed: bool = False
    passed: bool = False
    _min_dist: float = 1e9


@dataclass
class RoutePlan:
    unit_id: str
    incident_id: str
    cls: str
    stops: list = field(default_factory=list)   # ordered RouteStop, route order


class RouteCoordinator:
    def __init__(self, arm_lead_s: float = 25.0, pass_m: float = 60.0,
                 recede_m: float = 15.0, authorizer=None):
        # arm_lead_s: how many seconds before arrival to start clearing a junction.
        #   Must exceed worst-case clearance (min_green + amber + all-red) plus a
        #   margin for queue discharge — tune per corridor.
        self.arm_lead_s = arm_lead_s
        self.pass_m = pass_m
        self.recede_m = recede_m
        self.authorizer = authorizer         # callable(unit_id)->bool, e.g. Dispatcher.is_preempt_authorized
        self.plans: dict[str, RoutePlan] = {}

    def set_route(self, plan: RoutePlan) -> None:
        self.plans[plan.unit_id] = plan

    def clear_route(self, unit_id: str) -> list:
        """End the run: release every still-armed junction."""
        plan = self.plans.pop(unit_id, None)
        if not plan:
            return []
        return [("release", s.jid) for s in plan.stops if s.armed and not s.passed]

    def update(self, unit_id: str, etas: dict) -> list:
        """etas: jid -> (eta_s, dist_m) from live GPS. Returns arm/release actions."""
        plan = self.plans.get(unit_id)
        if not plan:
            return []
        # incident-bound gate: unauthorized unit gets nothing (and drops any holds)
        if self.authorizer is not None and not self.authorizer(unit_id):
            return self.clear_route(unit_id)

        actions = []
        for s in plan.stops:
            if s.passed:
                continue
            if s.jid in etas:
                s.eta_s, s.dist_m = etas[s.jid]
                s._min_dist = min(s._min_dist, s.dist_m)

            # arm ahead of arrival
            if not s.armed and s.eta_s <= self.arm_lead_s:
                s.armed = True
                actions.append(("arm", s.jid, plan.cls, plan.incident_id))

            # passed = got close, now receding
            if s.armed and s._min_dist <= self.pass_m and s.dist_m > s._min_dist + self.recede_m:
                s.passed = True
                actions.append(("release", s.jid))
        return actions

    def status(self, unit_id: str) -> list:
        plan = self.plans.get(unit_id)
        if not plan:
            return []
        return [{"jid": s.jid, "eta_s": round(s.eta_s, 1),
                 "armed": s.armed, "passed": s.passed} for s in plan.stops]
