from __future__ import annotations
"""Independent latching safety monitor (P2) — the software MMU (MON-1..7).

Watches COMMANDED LAMP OUTPUTS only (not FSM internals). On any fault it
latches and the engine forces flash-red at that junction. The corridor logic
cannot clear it: only an explicit external reset (ops action) can.
"""
from dataclasses import dataclass, field


@dataclass
class SafetyMonitor:
    jid: str
    amber_s: float
    allred_s: float
    min_green_s: float
    tolerance_s: float = 0.15
    heartbeat_timeout_s: float = 0.5

    latched: bool = False
    fault: str = ""
    _last: dict = field(default_factory=dict)      # previous lamps
    _dur: dict = field(default_factory=dict)       # how long current lamp state has held, per head
    _last_amber: dict = field(default_factory=dict)  # completed amber duration per head
    _last_allred: float = 0.0                        # completed all-red duration
    _allred_run: float = 0.0
    _last_tick: float = -1.0

    def trip(self, why: str) -> None:
        if not self.latched:
            self.latched = True
            self.fault = why

    def external_reset(self) -> None:
        """Only an operator may clear a fault — never the corridor logic."""
        self.latched = False
        self.fault = ""
        self._last = {}
        self._dur = {}
        self._allred_run = 0.0

    def observe(self, lamps: dict, dt: float, now: float) -> None:
        # watchdog: a hung engine must not hold live greens (MON-5)
        if self._last_tick >= 0 and (now - self._last_tick) > self.heartbeat_timeout_s:
            self.trip(f"watchdog: {now - self._last_tick:.2f}s since last tick")
        self._last_tick = now
        if self.latched:
            return

        ns, ew = lamps["ns"], lamps["ew"]
        # MON-1: conflicting non-red indications
        if ns != "red" and ew != "red":
            self.trip(f"conflicting indications ns={ns} ew={ew}")
            return

        prev = self._last
        if prev:
            for head in ("ns", "ew"):
                cur, was = lamps[head], prev[head]
                if cur == was:
                    self._dur[head] = self._dur.get(head, 0.0) + dt
                else:
                    held = self._dur.get(head, 0.0) + dt
                    # green ended: enforce min-green (FSM-4 backstop)
                    if was == "green" and held < self.min_green_s - self.tolerance_s:
                        self.trip(f"{head} green only {held:.2f}s < min_green")
                    # amber ended: record + enforce full amber (MON-4)
                    if was == "amber":
                        self._last_amber[head] = held
                        if held < self.amber_s - self.tolerance_s:
                            self.trip(f"{head} amber only {held:.2f}s")
                    # amber -> green forbidden (FSM-2 backstop)
                    if was == "amber" and cur == "green":
                        self.trip(f"{head} amber->green")
                    self._dur[head] = 0.0
            # all-red bookkeeping + green-onset clearance check (MON-4)
            both_red_now = ns == "red" and ew == "red"
            both_red_was = prev["ns"] == "red" and prev["ew"] == "red"
            if both_red_now:
                self._allred_run += dt
            for head in ("ns", "ew"):
                if lamps[head] == "green" and prev[head] != "green":
                    other = "ew" if head == "ns" else "ns"
                    other_was_green_recently = self._last_amber.get(other) is not None
                    if other_was_green_recently and not both_red_was:
                        self.trip(f"{head} green with no all-red before it")
                    elif other_was_green_recently and self._allred_run < self.allred_s - self.tolerance_s:
                        self.trip(f"{head} green after only {self._allred_run:.2f}s all-red")
            if not both_red_now:
                self._allred_run = 0.0
        self._last = dict(lamps)
