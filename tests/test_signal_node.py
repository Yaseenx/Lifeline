"""Embedded Intelligent Signal Module: an approaching emergency vehicle drives
the corridor to green through the SAFE FSM, and the signal reverts on its own —
with the independent monitor never tripping. Proves the edge unit is self-
sufficient (its own clock + fail-safe), not dependent on a central server."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "server"))

from signal_node import IntelligentSignal, SimApproachSource, SimLampDriver


class Clk:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def test_approach_grants_green_then_auto_reverts():
    clk = Clk()
    sig = IntelligentSignal("J1", SimApproachSource(), SimLampDriver(),
                            corridor_dir="EW", clock=clk)
    saw_green = saw_revert = False
    for _ in range(900):
        lamps = sig.tick(0.1); clk.t += 0.1
        if lamps.get("ew") == "green":
            saw_green = True
        if saw_green and sig.fsm.lease is None and sig.fsm.mode == "NORMAL":
            saw_revert = True
    assert saw_green, "never granted corridor green on approach"
    assert saw_revert, "never reverted after the vehicle passed"
    assert not sig.monitor.latched


def test_reverts_when_detection_goes_silent():
    """Detection/comms loss -> the signal stops being told to hold and reverts
    on its own; the independent monitor stays clean (no stuck green)."""
    clk = Clk()

    class Silent(SimApproachSource):
        def __init__(self): super().__init__(); self.dead = False
        def approaching(self, now):
            return [] if self.dead else super().approaching(now)

    src = Silent()
    sig = IntelligentSignal("J1", src, SimLampDriver(), corridor_dir="EW", clock=clk)
    for _ in range(250):          # let it engage (green/HOLD by ~t=20s)
        sig.tick(0.1); clk.t += 0.1
    assert sig.fsm.lease is not None and sig.fsm.mode == "HOLD"
    src.dead = True               # detection dies mid-approach
    for _ in range(60):
        sig.tick(0.1); clk.t += 0.1
    assert sig.fsm.lease is None, "lease survived detection loss"
    assert sig.fsm.mode in ("NORMAL", "EXIT_CLEAR")
    assert not sig.monitor.latched
