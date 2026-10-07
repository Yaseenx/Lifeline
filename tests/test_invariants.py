"""P2 GATE — the always-true oracle (Catalog §7), fuzzed.

Random preempt requests/renewals/releases hammer one junction for hours of
simulated time; every tick asserts the safety invariants. Any violation is a
bug, no matter the input sequence.
"""
import random
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "server"))

from controller import JunctionFSM
from monitor import SafetyMonitor

DT = 0.1
GREEN, AMBER, ALLRED, MING, MAXH, TTL = 9.0, 2.0, 1.5, 4.0, 20.0, 1.5


def make():
    f = JunctionFSM("J1", green_s=GREEN, amber_s=AMBER, allred_s=ALLRED,
                    min_green_s=MING, max_hold_s=MAXH, corridor_dir="EW")
    m = SafetyMonitor("J1", amber_s=AMBER, allred_s=ALLRED, min_green_s=MING)
    return f, m


class Oracle:
    """Tracks lamp history and asserts the invariants independently of both
    the FSM and the monitor implementations."""
    def __init__(self):
        self.prev = None
        self.amber_run = {"ns": 0.0, "ew": 0.0}
        self.green_run = {"ns": 0.0, "ew": 0.0}
        self.allred_run = 0.0

    def check(self, lamps, dt):
        ns, ew = lamps["ns"], lamps["ew"]
        # INV-1 no conflicting indications
        assert not (ns != "red" and ew != "red"), f"conflict {lamps}"
        if self.prev:
            for h in ("ns", "ew"):
                was, cur = self.prev[h], lamps[h]
                if was == "green":
                    self.green_run[h] += dt
                if was == "amber":
                    self.amber_run[h] += dt
                if was == "green" and cur != "green":
                    # INV-3 min green
                    assert self.green_run[h] >= MING - 0.11, f"{h} green {self.green_run[h]:.2f}"
                    # INV-2 green must end via amber, never straight to red
                    assert cur == "amber", f"{h} green->{cur}"
                    self.green_run[h] = 0.0
                if was == "amber" and cur != "amber":
                    assert cur == "red", f"{h} amber->{cur}"  # INV-2 no amber->green
                    assert self.amber_run[h] >= AMBER - 0.11, f"{h} amber {self.amber_run[h]:.2f}"
                    self.amber_run[h] = 0.0
                if cur == "green" and was != "green":
                    # INV-2 full all-red served before any green onset
                    assert self.allred_run >= ALLRED - 0.11, \
                        f"{h} green after {self.allred_run:.2f}s all-red"
            if ns == "red" and ew == "red":
                self.allred_run += dt
            else:
                self.allred_run = 0.0
        self.prev = dict(lamps)


def test_fuzz_preemption_invariants():
    random.seed(42)
    f, m = make()
    o = Oracle()
    now = 0.0
    epoch = 0
    green_since = None
    for step in range(120000):  # 200 minutes of sim time
        r = random.random()
        if r < 0.004:
            epoch += 1
            f.request_preempt(f"AMB-{random.randint(1,3)}", epoch, now, TTL)
        elif r < 0.006 and f.lease:
            f.renew(f.lease.owner, now, TTL)
        elif r < 0.008 and f.lease:
            f.release(f.lease.owner)
        f.tick(DT, now)
        lamps = f.lamps()
        m.observe(lamps, DT, now)
        o.check(lamps, DT)
        # INV-8 the monitor never trips on legitimate operation
        assert not m.latched, f"monitor tripped on legit ops: {m.fault} @step {step}"
        # INV-5 every hold is bounded: continuous green never exceeds
        # max_hold + clearance slack
        g = "ns" if lamps["ns"] == "green" else ("ew" if lamps["ew"] == "green" else None)
        if g:
            green_since = (green_since or now)
            assert now - green_since <= MAXH + GREEN + 1.0, "unbounded green"
        else:
            green_since = None
        now += DT


def test_monitor_latches_and_is_not_clearable_by_corridor():
    _, m = make()
    m.observe({"ns": "green", "ew": "red"}, 0.1, 0.0)
    m.observe({"ns": "green", "ew": "green"}, 0.1, 0.1)  # forced conflict
    assert m.latched and "conflict" in m.fault
    # corridor logic has no reset path; even feeding clean lamps stays latched
    for i in range(100):
        m.observe({"ns": "red", "ew": "red"}, 0.1, 0.2 + i * 0.1)
    assert m.latched
    m.external_reset()  # only the operator clears it
    assert not m.latched


def test_monitor_catches_short_clearance():
    _, m = make()
    t = 0.0
    # legit green for a while
    for _ in range(60):
        m.observe({"ns": "green", "ew": "red"}, 0.1, t); t += 0.1
    # amber far too short (0.3 s), then straight to the other green
    for _ in range(3):
        m.observe({"ns": "amber", "ew": "red"}, 0.1, t); t += 0.1
    m.observe({"ns": "red", "ew": "green"}, 0.1, t)
    assert m.latched, "short amber not caught"


def test_lease_expiry_reverts_hold():
    f, _ = make()
    now = 0.0
    f.request_preempt("AMB-1", 1, now, ttl_s=1.5)
    # drive to HOLD, renewing while the vehicle is 'approaching'
    for _ in range(300):
        f.renew("AMB-1", now, 1.5)
        f.tick(DT, now); now += DT
        if f.mode == "HOLD":
            break
    assert f.mode == "HOLD"
    # stop renewing: TTL must end the hold on its own (C9 / FAIL-2)
    for _ in range(40):
        f.tick(DT, now); now += DT
    assert f.mode in ("EXIT_CLEAR", "NORMAL"), f.mode
    assert f.lease is None
