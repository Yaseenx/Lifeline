from __future__ import annotations
"""Per-junction signal FSM — the ONLY thing that moves lamps (P1).

Safety rules built into the structure itself (Catalog FSM-1..8):
  * a head reaches green only through full AMBER + ALL-RED of the yielding
    direction — clearance can never be shortened or skipped
  * never amber -> green; after amber always all-red
  * min-green protected before any switch (normal or preempt entry/exit)
  * every preempt hold is time-bounded (max_hold_s) and auto-reverts
The corridor logic REQUESTS; this FSM disposes (ARB-5).
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Lease:
    owner: str
    epoch: int
    expires_at: float  # monotonic seconds; renewals push it forward


@dataclass
class JunctionFSM:
    jid: str
    green_s: float
    amber_s: float
    allred_s: float
    min_green_s: float
    max_hold_s: float
    corridor_dir: str = "EW"

    mode: str = "NORMAL"        # NORMAL | ENTRY_WAIT | ENTRY_CLEAR | HOLD | EXIT_CLEAR
    active: str = "NS"          # direction currently owning the cycle
    phase: str = "GREEN"        # GREEN | AMBER | ALLRED
    phase_age: float = 0.0
    hold_age: float = 0.0
    desired: Optional[str] = None
    lease: Optional[Lease] = None
    events: list = field(default_factory=list)  # (kind, detail) appended per tick

    # ---------------- lamp output (what the monitor watches) ----------------
    def lamps(self) -> dict:
        ns = ew = "red"
        if self.phase in ("GREEN", "AMBER"):
            lamp = "green" if self.phase == "GREEN" else "amber"
            if self.active == "NS":
                ns = lamp
            else:
                ew = lamp
        return {"ns": ns, "ew": ew}

    # ---------------- corridor-facing API ----------------
    def request_preempt(self, owner: str, epoch: int, now: float, ttl_s: float) -> str:
        """Ask for corridor_dir green. Returns granted|entering|rejected."""
        if self.lease and self.lease.owner != owner:
            return "rejected"  # single owner per junction (ARB-4); arbiter queues
        if self.lease and epoch < self.lease.epoch:
            return "rejected"  # stale writer (FAIL-5)
        self.lease = Lease(owner=owner, epoch=epoch, expires_at=now + ttl_s)
        self.desired = self.corridor_dir
        if self.mode in ("HOLD",):
            return "granted"
        if self.mode == "NORMAL":
            self.mode = "ENTRY_WAIT"
        return "entering"

    def renew(self, owner: str, now: float, ttl_s: float) -> bool:
        if self.lease and self.lease.owner == owner:
            self.lease.expires_at = now + ttl_s
            return True
        return False

    def release(self, owner: str) -> None:
        if self.lease and self.lease.owner == owner:
            self._end_preempt("released")

    def _end_preempt(self, why: str) -> None:
        self.lease = None
        self.desired = None
        if self.mode == "HOLD":
            self.mode = "EXIT_CLEAR"   # leave through amber+all-red, never snap
        elif self.mode in ("ENTRY_WAIT", "ENTRY_CLEAR"):
            self.mode = "NORMAL"       # never got the green; resume cycling
        self.events.append(("preempt_end", why))

    # ---------------- tick ----------------
    def tick(self, dt: float, now: float) -> None:
        self.events.clear()
        # lease TTL is the comms-loss fail-safe (FSM-8 / FAIL-2)
        if self.lease and now >= self.lease.expires_at:
            self._end_preempt("lease_expired")
        if self.mode == "HOLD":
            self.hold_age += dt
            if self.hold_age >= self.max_hold_s:
                self._end_preempt("max_hold")  # no open-ended greens, ever
        self.phase_age += dt

        if self.phase == "GREEN":
            self._tick_green()
        elif self.phase == "AMBER":
            if self.phase_age >= self.amber_s:
                self._set_phase("ALLRED")
        elif self.phase == "ALLRED":
            if self.phase_age >= self.allred_s:
                self._leave_allred()

    def _tick_green(self) -> None:
        if self.mode == "HOLD":
            return  # held green; bounded by max_hold + lease TTL above
        if self.mode == "ENTRY_WAIT":
            if self.active == self.desired:
                self.mode = "HOLD"      # already green in the corridor direction
                self.hold_age = 0.0
                self.events.append(("granted", self.jid))
                return
            if self.phase_age >= self.min_green_s:
                self.mode = "ENTRY_CLEAR"
                self._set_phase("AMBER")  # clear the conflicting green safely
            return
        # NORMAL or EXIT already handled; normal green runs its course
        if self.phase_age >= self.green_s:
            self._set_phase("AMBER")

    def _leave_allred(self) -> None:
        if self.mode == "ENTRY_CLEAR" and self.desired:
            self.active = self.desired
            self._set_phase("GREEN")
            self.mode = "HOLD"
            self.hold_age = 0.0
            self.events.append(("granted", self.jid))
        elif self.mode == "EXIT_CLEAR":
            self.active = "EW" if self.active == "NS" else "NS"
            self._set_phase("GREEN")
            self.mode = "NORMAL"
            self.events.append(("resumed", self.jid))
        else:
            self.active = "EW" if self.active == "NS" else "NS"
            self._set_phase("GREEN")

    def _set_phase(self, phase: str) -> None:
        # min-green guard: leaving GREEN before min_green is a structural bug
        if self.phase == "GREEN" and phase == "AMBER" and self.phase_age < self.min_green_s - 1e-9:
            raise AssertionError(f"{self.jid}: min-green violated ({self.phase_age:.2f}s)")
        if self.phase == "AMBER" and phase == "GREEN":
            raise AssertionError(f"{self.jid}: amber->green forbidden")
        self.phase = phase
        self.phase_age = 0.0
