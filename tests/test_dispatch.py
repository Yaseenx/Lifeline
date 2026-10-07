"""Dispatch brain: nearest-available assignment and incident-bound preemption
(a unit earns a corridor only when it's dispatched to an active incident)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "server"))

from dispatch import Dispatcher, Unit, UnitStatus, IncidentStatus


class Clk:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def _fleet():
    d = Dispatcher(clock=Clk())
    d.register_unit(Unit(id="AMB-A", lat=13.10, lng=80.30))    # far NE
    d.register_unit(Unit(id="AMB-B", lat=13.081, lng=80.276))  # near MMC
    d.register_unit(Unit(id="AMB-C", lat=13.05, lng=80.20))    # far SW
    return d


def test_nearest_available_picks_closest():
    assert _fleet().nearest_available(13.0809, 80.2757).id == "AMB-B"


def test_assign_binds_and_authorizes():
    d = _fleet()
    inc = d.create_incident(13.0809, 80.2757, type="road_accident", reported_via="whatsapp")
    u = d.assign(inc.id)
    assert u.id == "AMB-B"
    assert d.units["AMB-B"].status == UnitStatus.ASSIGNED
    assert d.incidents[inc.id].status == IncidentStatus.ASSIGNED
    assert d.is_preempt_authorized("AMB-B") is True


def test_unassigned_unit_not_authorized():
    d = _fleet()
    assert d.is_preempt_authorized("AMB-A") is False   # no incident -> no corridor
    assert d.is_preempt_authorized("NOPE") is False


def test_close_frees_unit_and_deauthorizes():
    d = _fleet()
    inc = d.create_incident(13.0809, 80.2757)
    u = d.assign(inc.id)
    d.close_incident(inc.id)
    assert d.units[u.id].status == UnitStatus.AVAILABLE
    assert d.is_preempt_authorized(u.id) is False


def test_no_unit_free_returns_none():
    d = Dispatcher(clock=Clk())
    d.register_unit(Unit(id="AMB-A", status=UnitStatus.OOS))
    inc = d.create_incident(13.0, 80.0)
    assert d.assign(inc.id) is None
