"""WhatsApp intake: classify a bystander message, parse Meta's location webhook
shape, and create + auto-dispatch an incident."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "server"))

import intake
from dispatch import Dispatcher, Unit


class Clk:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def _fleet():
    d = Dispatcher(clock=Clk())
    d.register_unit(Unit(id="AMB-A", lat=13.10, lng=80.30))
    d.register_unit(Unit(id="AMB-B", lat=13.081, lng=80.276))
    d.register_unit(Unit(id="AMB-C", lat=13.05, lng=80.20))
    return d


def test_classify():
    assert intake.classify("major accident, person bleeding")[0] == "road_accident"
    assert intake.classify("building on fire, smoke everywhere")[0] == "fire"
    assert intake.classify("someone collapsed")[0] == "medical"


def test_parse_whatsapp_location_valid_and_invalid():
    good = {"entry": [{"changes": [{"value": {"messages": [
        {"location": {"latitude": 13.079, "longitude": 80.244}, "text": {"body": "accident"}}]}}]}]}
    p = intake.parse_whatsapp_location(good)
    assert p and abs(p["lat"] - 13.079) < 1e-9 and p["text"] == "accident"
    assert intake.parse_whatsapp_location({"foo": 1}) is None
    text_only = {"entry": [{"changes": [{"value": {"messages": [{"text": {"body": "hi"}}]}}]}]}
    assert intake.parse_whatsapp_location(text_only) is None


def test_handle_report_creates_and_assigns():
    d = _fleet()
    res = intake.handle_report(d, 13.0809, 80.2757, "accident near MMC", via="whatsapp")
    assert res.accepted and res.unit.id == "AMB-B"
    assert res.incident.reported_via == "whatsapp"
    assert d.is_preempt_authorized("AMB-B")
