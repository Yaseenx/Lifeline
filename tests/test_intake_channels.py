"""Multi-channel intake: phone-call (operator types address -> geocoded),
call-taker type/priority override, geocode-failure handling, and the WhatsApp
pin path still working."""
import sys, pathlib, asyncio
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "server"))

import intake
from dispatch import Dispatcher, Unit


def _fleet():
    d = Dispatcher()
    d.register_unit(Unit(id="AMB-A", lat=13.10, lng=80.30))
    d.register_unit(Unit(id="AMB-B", lat=13.081, lng=80.276))
    d.register_unit(Unit(id="AMB-C", lat=13.05, lng=80.20))
    return d


def test_operator_address_intake_geocoded():
    d = _fleet()

    async def fake_geo(addr, city_bias="Chennai, Tamil Nadu, India"):
        assert "kilpauk" in addr.lower()
        return (13.0790, 80.2445, "Kilpauk, Chennai")

    res = asyncio.run(intake.report_from_address(
        d, "Kilpauk Medical College Rd", text="car crash, 2 injured", via="call", geocoder=fake_geo))
    assert res.accepted and res.unit is not None
    assert res.incident.reported_via == "call"
    assert res.incident.address == "Kilpauk Medical College Rd"
    assert res.incident.type == "road_accident"


def test_operator_type_override():
    d = _fleet()
    res = intake.handle_report(d, 13.08, 80.27, text="unclear", via="call",
                               incident_type="medical", priority="code_red")
    assert res.incident.type == "medical" and res.incident.priority == "code_red"


def test_geocode_failure_not_accepted():
    d = _fleet()

    async def none_geo(addr, city_bias=""):
        return None

    res = asyncio.run(intake.report_from_address(d, "asdfqwer", geocoder=none_geo))
    assert not res.accepted and res.incident is None


def test_whatsapp_pin_still_works():
    d = _fleet()
    pl = {"entry": [{"changes": [{"value": {"messages": [
        {"location": {"latitude": 13.0809, "longitude": 80.2757}, "text": {"body": "accident"}}]}}]}]}
    loc = intake.parse_whatsapp_location(pl)
    res = intake.handle_report(d, loc["lat"], loc["lng"], loc["text"], via="whatsapp")
    assert res.accepted and res.incident.reported_via == "whatsapp"
