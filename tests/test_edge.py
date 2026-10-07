"""Edge signal node: drives its own junction's lamps from the server feed,
flashes red on a FAULT, and — critically — flashes red on its OWN watchdog when
commands stop (the field-side fail-safe; no stuck green if the server dies)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "server"))

from edge_signal import EdgeSignal


class FakeDriver:
    def __init__(self): self.applied = []; self.flashes = []
    def apply(self, lamps): self.applied.append(dict(lamps))
    def flash_red(self, why=""): self.flashes.append(why)


class Clk:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def snap(jid, lamps, mode="HOLD", fault=""):
    return {"junctions": [{"id": jid, "lamps": lamps, "mode": mode, "fault": fault},
                          {"id": "J2", "lamps": {"ns": "red", "ew": "green"}, "mode": "NORMAL"}]}


def test_drives_this_junctions_lamps():
    d = FakeDriver(); n = EdgeSignal("J1", d, watchdog_s=1.0, clock=Clk())
    n.on_snapshot(snap("J1", {"ns": "red", "ew": "green"}))
    assert d.applied[-1] == {"ns": "red", "ew": "green"} and not d.flashes


def test_fault_flashes_red():
    d = FakeDriver(); n = EdgeSignal("J1", d, clock=Clk())
    n.on_snapshot(snap("J1", {"ns": "flash", "ew": "flash"}, mode="FAULT", fault="conflict"))
    assert d.flashes and "conflict" in d.flashes[-1]


def test_watchdog_flashes_on_comms_loss():
    clk = Clk(); d = FakeDriver(); n = EdgeSignal("J1", d, watchdog_s=1.0, clock=clk)
    n.on_snapshot(snap("J1", {"ns": "red", "ew": "green"}))   # last command at t=0
    clk.t = 0.5
    assert n.check_watchdog() is False                        # still within window
    clk.t = 1.6
    assert n.check_watchdog() is True                         # exceeded -> flash red
    assert "comms loss" in d.flashes[-1]


def test_ignores_other_junctions():
    d = FakeDriver(); n = EdgeSignal("J1", d, clock=Clk())
    n.on_snapshot({"junctions": [{"id": "J2", "lamps": {"ns": "green", "ew": "red"}, "mode": "HOLD"}]})
    assert not d.applied and not d.flashes and n.received is False
