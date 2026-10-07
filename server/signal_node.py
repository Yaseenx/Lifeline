from __future__ import annotations
"""
Intelligent Signal Module (ISM) — the embedded, on-the-junction unit.

Runs AT one signal. Reuses the PROVEN safe core (controller.JunctionFSM +
monitor.SafetyMonitor + arbiter.JunctionArbiter) and wraps it so a single
signal can decide LOCALLY to go green as an emergency vehicle approaches, and
REVERT ON ITS OWN if it loses contact.

Why embedded (fixes the C3 gap): today the central corridor server drives every
junction; if it stalls, nothing at the junction reverts. An embedded module
gives each signal its own clock, its own lease TTL fail-safe, and its own
independent monitor — the field-side safety executor. The central server, when
present, only sends priority REQUESTS (NTCIP-1211-style); the signal disposes,
safely, on its own.

REAL here: the decision + safe FSM + monitor + TTL revert (runs in sim below).
STUBBED (hardware/integration): how the signal DETECTS an approach, and how
commanded lamps reach the real controller. Those sit behind two interfaces so
the safety core never changes when you swap sim for silicon.
"""
import time
from dataclasses import dataclass

from controller import JunctionFSM
from monitor import SafetyMonitor
from arbiter import JunctionArbiter


# ---- hardware/integration boundaries (swap sim for silicon here) ----------

class ApproachSource:
    """How the signal learns a vehicle is approaching. Implement one of:
      * onboard GPS beacon over C-V2X / DSRC (vehicle broadcasts signed pos)
      * a relayed priority request from the central corridor server
      * a local radio / optical emitter (Opticom-style)
    Must return authenticated detections only."""
    def approaching(self, now: float) -> list:
        raise NotImplementedError


class LampDriver:
    """How commanded lamps reach the real signal. Implement over NTCIP 1211
    (signal priority) to the intersection controller, or GPIO to a cabinet.
    flash_red() is the fail-safe the hardware conflict monitor also enforces."""
    def apply(self, lamps: dict) -> None:
        raise NotImplementedError
    def flash_red(self, why: str) -> None:
        raise NotImplementedError


# ---- desk-test implementations (make the module runnable now) -------------

class SimApproachSource(ApproachSource):
    """Scripted vehicle approaching then receding, for local testing."""
    def __init__(self, cls="code_red", start_m=600.0, speed_mps=12.0):
        self.cls, self.dist, self.speed = cls, start_m, speed_mps
        self.t0 = None
    def approaching(self, now):
        if self.t0 is None:
            self.t0 = now
        d = self.dist - self.speed * (now - self.t0)   # closes, then goes negative (passed)
        return [{"id": "AMB-1", "cls": self.cls, "sos": True, "sos_ts": self.t0,
                 "dist_m": abs(d), "approaching": d > 0}]


class SimLampDriver(LampDriver):
    def __init__(self): self.last = None; self.faulted = False
    def apply(self, lamps): self.last = dict(lamps); self.faulted = False
    def flash_red(self, why): self.last = {"ns": "flash", "ew": "flash"}; self.faulted = True


# ---- the embedded module --------------------------------------------------

@dataclass
class SignalTimings:
    green_s: float = 9.0
    amber_s: float = 2.0
    allred_s: float = 1.5
    min_green_s: float = 4.0
    max_hold_s: float = 90.0
    lead_m: float = 450.0     # start preempting inside this distance
    pass_m: float = 60.0      # past + receding -> release
    ttl_s: float = 1.5        # no renewal within this -> auto-revert (fail-safe)


class IntelligentSignal:
    def __init__(self, jid: str, source: ApproachSource, driver: LampDriver,
                 corridor_dir: str = "EW", timings: SignalTimings | None = None,
                 clock=time.monotonic):
        t = timings or SignalTimings()
        self.jid, self.t, self.clock = jid, t, clock
        self.source, self.driver = source, driver
        self.fsm = JunctionFSM(jid, t.green_s, t.amber_s, t.allred_s,
                               t.min_green_s, t.max_hold_s, corridor_dir)
        self.monitor = SafetyMonitor(jid, t.amber_s, t.allred_s, t.min_green_s)
        self.arb = JunctionArbiter(jid)

    def tick(self, dt: float) -> dict:
        now = self.clock()
        t = self.t
        dets = self.source.approaching(now)
        cand = [v for v in dets if v.get("sos") and v["dist_m"] < t.lead_m
                and (v.get("approaching") or v["dist_m"] < t.pass_m * 2)]

        for v in cand:
            st = self.arb.state_for(v["id"])
            if st == "none":
                if self.arb.request(v["id"], v["cls"], v["sos_ts"]) == "owner":
                    self.fsm.request_preempt(v["id"], self.arb.epoch, now, t.ttl_s)
            elif st == "owner":
                if self.fsm.lease is None or self.fsm.lease.owner != v["id"]:
                    self.fsm.request_preempt(v["id"], self.arb.epoch, now, t.ttl_s)
                self.fsm.renew(v["id"], now, t.ttl_s)

        present = {v["id"] for v in cand}
        owner = self.arb.owner.amb_id if self.arb.owner else None
        # candidate gone -> release and promote the queue
        if owner and owner not in present:
            self.fsm.release(owner)
            nxt = self.arb.release(owner)
            owner = nxt.amb_id if nxt else None
            if owner:
                self.fsm.request_preempt(owner, self.arb.epoch, now, t.ttl_s)
        # override reconciliation: if the arbiter changed owner (a higher class
        # took over) hand the FSM over NOW rather than waiting for TTL — this is
        # the C2 fix from the review, applied locally at the signal.
        if owner and self.fsm.lease and self.fsm.lease.owner != owner:
            self.fsm.release(self.fsm.lease.owner)
            self.fsm.request_preempt(owner, self.arb.epoch, now, t.ttl_s)

        self.fsm.tick(dt, now)
        lamps = self.fsm.lamps()
        self.monitor.observe(lamps, dt, now)
        if self.monitor.latched:
            self.driver.flash_red(self.monitor.fault)   # unclearable except by ops
        else:
            self.driver.apply(lamps)
        return {"ns": "flash", "ew": "flash"} if self.monitor.latched else lamps


# ---- runnable demo: one approach engages green, passing reverts it ---------
def _demo():
    class Clk:
        def __init__(self): self.t = 0.0
        def __call__(self): return self.t
    clk = Clk()
    sig = IntelligentSignal("J1", SimApproachSource(), SimLampDriver(),
                            corridor_dir="EW", clock=clk)
    saw_green_ew = saw_revert = False
    for _ in range(900):  # 90 s
        lamps = sig.tick(0.1); clk.t += 0.1
        if lamps.get("ew") == "green":
            saw_green_ew = True
        if saw_green_ew and sig.fsm.lease is None and sig.fsm.mode == "NORMAL":
            saw_revert = True
    assert saw_green_ew, "signal never granted the corridor green on approach"
    assert saw_revert, "signal never reverted after the vehicle passed"
    assert not sig.monitor.latched, "monitor tripped on legit operation"
    print("ISM demo: approach -> corridor GREEN, pass -> auto-revert, monitor clean. PASS")


if __name__ == "__main__":
    _demo()
