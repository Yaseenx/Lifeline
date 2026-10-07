"""App-level integration: boot the REAL FastAPI server (app.py) and drive it
through its HTTP endpoints — intake -> dispatch -> state, call validation, and
the WhatsApp webhook handshake. Needs the server deps (fastapi, httpx). Skips
cleanly if they aren't installed."""
import os
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "server"))
os.environ.setdefault("WA_VERIFY_TOKEN", "testtok")
os.environ.setdefault("OPS_TOKEN", "opssecret")

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
import app as A

client = TestClient(A.api)


def test_health():
    assert client.get("/health").json()["ok"] is True


def test_whatsapp_intake_dispatches_and_shows_in_state():
    A.engine.telemetry({"device_id": "AMB-CHN-001", "lat": 13.0809, "lng": 80.2757,
                        "speed_kph": 20, "sos": True, "trip_id": "T1"})
    r = client.post("/intake/whatsapp", json={"lat": 13.0809, "lng": 80.2757, "text": "accident, bleeding"})
    body = r.json()
    assert r.status_code == 200 and body["accepted"] is True
    assert body["unit"] == "AMB-CHN-001"
    assert body["incident"]["type"] == "road_accident"
    s = client.get("/state").json()
    assert any(i["unit"] == "AMB-CHN-001" for i in s["incidents"])
    assert any(a["id"] == "AMB-CHN-001" for a in s["ambulances"])


def test_call_intake_requires_address():
    assert client.post("/intake/call", json={"address": ""}).status_code == 400


def test_call_intake_with_injected_geocoder():
    import intake as I

    async def fake_geo(addr, city_bias="Chennai, Tamil Nadu, India"):
        return (13.0790, 80.2445, "Kilpauk, Chennai")

    orig = A.engine.dispatch_call

    async def patched(address, text="", incident_type=None, priority=None):
        return await I.report_from_address(A.engine.dispatcher, address, text=text,
                                           via="call", incident_type=incident_type,
                                           priority=priority, geocoder=fake_geo)

    A.engine.dispatch_call = patched
    A.engine.telemetry({"device_id": "AMB-CHN-002", "lat": 13.0790, "lng": 80.2445,
                        "speed_kph": 15, "sos": True, "trip_id": "T2"})
    r = client.post("/intake/call", json={"address": "Kilpauk MCH Rd",
                                          "type": "road_accident", "priority": "code_red"})
    A.engine.dispatch_call = orig
    body = r.json()
    assert r.status_code == 200 and body["accepted"] is True
    assert body["unit"] in ("AMB-CHN-001", "AMB-CHN-002")


def test_wa_webhook_verify():
    ok = client.get("/wa/webhook", params={"hub.mode": "subscribe",
                    "hub.verify_token": "testtok", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    bad = client.get("/wa/webhook", params={"hub.mode": "subscribe",
                     "hub.verify_token": "wrong", "hub.challenge": "42"})
    assert bad.status_code == 403


def test_ops_control_requires_auth():
    jid = A.engine.cfg.junctions[0].id
    A.engine.monitors[jid].trip("drill")
    A._apply_ops_command({"type": "monitor_reset", "junction": jid}, authed=False)
    assert A.engine.monitors[jid].latched, "unauthenticated reset must be rejected"
    A._apply_ops_command({"type": "monitor_reset", "junction": jid}, authed=True)
    assert not A.engine.monitors[jid].latched, "authenticated reset should work"


def test_ws_auth_logic():
    ws_remote = type("W", (), {"client": type("C", (), {"host": "9.9.9.9"})()})()
    ws_local = type("W", (), {"client": type("C", (), {"host": "127.0.0.1"})()})()
    saved = A._ops_token
    A._ops_token = "opssecret"                      # token set -> must match
    assert A._ws_authed(ws_remote, "opssecret") and not A._ws_authed(ws_remote, "x")
    A._ops_token = ""                               # no token -> localhost only
    assert A._ws_authed(ws_local, "") and not A._ws_authed(ws_remote, "")
    A._ops_token = saved
