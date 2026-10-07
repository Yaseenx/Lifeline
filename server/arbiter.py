from __future__ import annotations
"""Arbiter + leases (P3): who gets each junction (ARB-1..8, FAIL-5).

Priority: CODE_RED > CODE_BLUE; FCFS within a class (earlier sos_ts wins);
stable tie-break on id. One owner per junction; a higher class OVERRIDES an
active lower one; the rest wait in a bounded queue. Every grant carries a
monotonically increasing writer epoch (split-brain fencing).
"""
from dataclasses import dataclass, field

CLASS_RANK = {"code_red": 2, "code_blue": 1}
MAX_QUEUE = 8  # ARB-8: bounded against request floods


@dataclass(order=True)
class Req:
    sort_key: tuple = field(init=False, repr=False)
    amb_id: str = field(compare=False)
    cls: str = field(compare=False)
    sos_ts: float = field(compare=False)

    def __post_init__(self):
        # smaller sorts first: higher class first, then earlier sos, then id
        self.sort_key = (-CLASS_RANK.get(self.cls, 0), self.sos_ts, self.amb_id)


class JunctionArbiter:
    def __init__(self, jid: str):
        self.jid = jid
        self.owner: Req | None = None
        self.queue: list[Req] = []
        self.epoch = 0

    def request(self, amb_id: str, cls: str, sos_ts: float) -> str:
        """Returns owner|queued|rejected for this ambulance at this junction."""
        r = Req(amb_id=amb_id, cls=cls, sos_ts=sos_ts)
        if self.owner and self.owner.amb_id == amb_id:
            return "owner"
        if self.owner is None:
            self.owner = r
            self.epoch += 1
            return "owner"
        # ARB-4: a higher preempt overrides an active lower one
        if r.sort_key < self.owner.sort_key:
            demoted = self.owner
            self.owner = r
            self.epoch += 1
            self._enqueue(demoted)
            return "owner"
        return "queued" if self._enqueue(r) else "rejected"

    def _enqueue(self, r: Req) -> bool:
        if any(q.amb_id == r.amb_id for q in self.queue):
            return True
        if len(self.queue) >= MAX_QUEUE:
            return False
        self.queue.append(r)
        self.queue.sort()
        return True

    def release(self, amb_id: str) -> Req | None:
        """Owner leaves; next queued (if any) becomes owner. Returns new owner."""
        if self.owner and self.owner.amb_id == amb_id:
            self.owner = None
            if self.queue:
                self.owner = self.queue.pop(0)
                self.epoch += 1
            return self.owner
        self.queue = [q for q in self.queue if q.amb_id != amb_id]
        return None

    def state_for(self, amb_id: str) -> str:
        if self.owner and self.owner.amb_id == amb_id:
            return "owner"
        if any(q.amb_id == amb_id for q in self.queue):
            return "queued"
        return "none"
