"""Fire scaffold: prove it reserves priority BELOW ambulance, the default stays
ambulance-only, and the unbuilt parts fail loudly — without disturbing the rest
of the suite (ranks are restored after each test)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "server"))

import pytest
import arbiter
from arbiter import Req
import fire

ORIGINAL = dict(arbiter.CLASS_RANK)  # snapshot before any register()


@pytest.fixture(autouse=True)
def _restore_ranks():
    yield
    arbiter.CLASS_RANK.clear()
    arbiter.CLASS_RANK.update(ORIGINAL)


def test_default_is_ambulance_only():
    assert "fire_major" not in ORIGINAL
    assert set(ORIGINAL) <= {"code_red", "code_blue"}


def test_register_keeps_every_ambulance_above_every_fire():
    fire.register()
    r = arbiter.CLASS_RANK
    assert min(r["code_red"], r["code_blue"]) > max(
        r["fire_major"], r["fire_standard"], r["fire_support"])


def test_ambulance_outranks_fire_even_when_fire_called_first():
    fire.register()
    amb = Req(amb_id="AMB", cls="code_blue", sos_ts=100.0)   # lower amb class, later
    fir = Req(amb_id="FIRE", cls="fire_major", sos_ts=50.0)  # top fire class, earlier
    assert amb.sort_key < fir.sort_key  # smaller sorts first = higher priority


def test_unbuilt_parts_raise():
    with pytest.raises(NotImplementedError):
        fire.dispatch_fire(None, [])
    with pytest.raises(NotImplementedError):
        fire.clearance_profile("fire_major")
    with pytest.raises(NotImplementedError):
        fire.convoy_owner("INC1", ["A"])
