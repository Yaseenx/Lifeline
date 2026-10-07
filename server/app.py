from __future__ import annotations
"""Realtime gateway: FastAPI + native WS for ops, a Socket.IO endpoint for the
vehicle agent, and REAL intake — a call-taker REST endpoint (operator types an
address) and the WhatsApp Business webhook. Every vehicle event is verified at
ingress. Run:  uvicorn app:app --port 4000
"""
import asyncio
import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import socketio
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, HTMLResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

import topology
from engine import Engine
from security import Ingress
import intake
import live_signals
import local_signals
import hospitals
from whatsapp import WhatsAppClient, sender_of

cfg = topology.load()
engine = Engine(cfg)
ingress = Ingress(cfg.devices, cfg.freshness_window_s)
wa = WhatsAppClient()
_ops_token = os.getenv("OPS_TOKEN", "")           # required for ops CONTROL over /ws
CONTROL_CMDS = {"kill_server", "restore", "monitor_reset", "close_incident"}

api = FastAPI(title="LifeLine corridor server")
# The ambulance dashboard runs on a different port; let it read the read-only
# data endpoints (/hospitals bed availability, /signals, /state) cross-origin.
from fastapi.middleware.cors import CORSMiddleware
api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
app = socketio.ASGIApp(sio, other_asgi_app=api)

ops_clients: set[WebSocket] = set()
device_sids: dict[str, str] = {}
rejects = 0
_route_anchor: dict[str, tuple] = {}   # unit -> (dest_key, lat, lng) of the last route we built
ROUTE_REFRESH_S = 1.0                   # how often the route loop wakes (a new trip is picked up within this)
ROUTE_MOVE_M = 300.0                    # rebuild the route after the unit drifts this far


def _reply_text(res) -> str:
    if not res or not res.accepted:
        return "Could not dispatch — location not recognised. Please resend the address/pin."
    inc, unit = res.incident, res.unit
    return f"Ambulance {unit.id} dispatched (incident {inc.id}). Help is on the way."


# ---------------- vehicle gateway (Socket.IO) ----------------
@sio.event
async def connect(sid, environ, auth):
    ok, why = ingress.verify(auth or {})
    if not ok:
        engine._log("auth_reject", str((auth or {}).get("device_id")), "", why)
        return False
    device_sids[(auth or {}).get("device_id")] = sid
    engine._log("agent_connect", (auth or {}).get("device_id", "?"), "", "")


def _verified(handler):
    async def wrap(sid, data):
        global rejects
        ok, why = ingress.verify(data if isinstance(data, dict) else {})
        if not ok:
            rejects += 1
            engine._log("msg_reject", str((data or {}).get("device_id")), "", why)
            return
        await handler(sid, data)
    return wrap


@sio.on("vehicle:telemetry")
@_verified
async def on_telemetry(sid, data):
    engine.telemetry(data)


@sio.on("vehicle:sos")
@_verified
async def on_sos(sid, data):
    engine.sos(data)
    if data.get("active"):
        await sio.emit("trip:ack", {"trip_id": data.get("trip_id"), "accepted": True}, to=sid)


@sio.on("vehicle:trip")
@_verified
async def on_trip(sid, data):
    engine.trip(data)


@sio.on("vehicle:hazard_ack")
@_verified
async def on_hazard_ack(sid, data):
    engine._log("hazard_ack", data.get("device_id", "?"), data.get("node_id", ""), "")


@sio.on("vehicle:dispatch_ack")
@_verified
async def on_dispatch_ack(sid, data):
    # Crew accepted/declined the assignment. On decline, free the unit so it can
    # be reassigned; accept needs no server action (the trip authorizes itself).
    if not data.get("accepted") and data.get("incident_id"):
        engine.close_incident(data["incident_id"])
        engine._log("dispatch_declined", data.get("device_id", "?"), "", data["incident_id"])


# ---------------- intake: call-taker (REST) ----------------
@api.post("/intake/call")
async def intake_call(req: Request):
    """A human call-taker submits the accident ADDRESS + details."""
    d = await req.json()
    address = (d.get("address") or "").strip()
    if not address:
        return JSONResponse({"accepted": False, "error": "address required"}, status_code=400)
    res = await engine.dispatch_call(address, text=d.get("text", ""),
                                     incident_type=d.get("type"), priority=d.get("priority"))
    await _notify_assigned(res)
    return JSONResponse(_result_json(res))


@api.post("/intake/whatsapp")
async def intake_whatsapp(req: Request):
    d = await req.json()
    try:
        lat, lng = float(d["lat"]), float(d["lng"])
    except (KeyError, TypeError, ValueError):
        return JSONResponse({"accepted": False, "error": "lat/lng required"}, status_code=400)
    res = engine.dispatch_whatsapp(lat, lng, text=d.get("text", ""))
    await _notify_assigned(res)
    return JSONResponse(_result_json(res))


def _result_json(res) -> dict:
    if not res or not res.incident:
        return {"accepted": False,
                "error": "could not resolve the address — check internet, or type 'lat, lng'"}
    inc = res.incident
    out = {"accepted": bool(res.accepted),
           "incident": {"id": inc.id, "type": inc.type, "priority": inc.priority,
                        "lat": inc.lat, "lng": inc.lng, "address": inc.address,
                        "via": inc.reported_via},
           "unit": (res.unit.id if res.unit else None)}
    if not res.unit:
        out["error"] = "no ambulance available (none registered/idle)"
    return out


async def _notify_assigned(res) -> None:
    """Push the assignment to the assigned unit's agent so the crew gets an
    Accept/Decline prompt on the vehicle dashboard."""
    if not (res and res.accepted and res.unit):
        return
    sid = device_sids.get(res.unit.id)
    if not sid:
        return
    inc = res.incident
    await sio.emit("dispatch:assign", {
        "incident_id": inc.id, "type": inc.type, "priority": inc.priority,
        "lat": inc.lat, "lng": inc.lng, "address": inc.address}, to=sid)
    engine._log("dispatch_assign", res.unit.id, "", inc.id)


# ---------------- intake: WhatsApp Business webhook ----------------
@api.get("/wa/webhook")
async def wa_verify(req: Request):
    challenge = wa.verify_webhook(dict(req.query_params))
    if challenge is not None:
        return PlainTextResponse(challenge)
    return PlainTextResponse("forbidden", status_code=403)


@api.post("/wa/webhook")
async def wa_inbound(req: Request):
    payload = await req.json()
    loc = intake.parse_whatsapp_location(payload)
    if loc:
        res = engine.dispatch_whatsapp(loc["lat"], loc["lng"], text=loc.get("text", ""))
        await _notify_assigned(res)
        to = sender_of(payload)
        if to:
            await wa.send_text(to, _reply_text(res))
    return JSONResponse({"ok": True})


# ---------------- ops console (native WS + static pages) ----------------
@api.get("/")
async def index():
    return FileResponse(__file__.replace("app.py", "ops.html"))


@api.get("/console")
async def console():
    # Inject the Google Maps key so the console can do Places autocomplete +
    # geocoding in the browser (real "type the address, it finds it" UX).
    import pathlib
    html = pathlib.Path(__file__).with_name("console.html").read_text()
    html = html.replace("{{MAPS_KEY}}", os.getenv("GOOGLE_MAPS_API_KEY", ""))
    return HTMLResponse(html)


@api.get("/state")
async def state():
    return JSONResponse(engine.snapshot())


@api.get("/health")
async def health():
    return JSONResponse({"ok": True, "tick": engine.tick_n, "online": engine.online,
                         "rejected_msgs": rejects})


@api.get("/signals")
async def signals_dataset():
    """Read-only: the mapped traffic signals from the local dataset, for the ops
    map's placeholder layer. Empty list if no dataset is present."""
    return JSONResponse({"signals": local_signals.all_features(),
                         "count": local_signals.count()})


# ---------------- Hospital console (monitor inbound + bed availability) ----------------
def _inbound_for(h, snap):
    """Ambulances in the live snapshot whose destination is this hospital."""
    hid = h["id"]; hname = (h.get("name") or "").lower()
    out = []
    for a in snap.get("ambulances", []):
        if not a.get("active"):
            continue
        dest = a.get("dest") or {}
        if not (dest.get("id") == hid or (dest.get("name") or "").lower() == hname):
            continue
        has_fix = a.get("has_fix", False)
        # ETA + distance are computed ONCE by the engine (road route, ETA floor) and
        # carried in the snapshot. The hospital console shows the SAME numbers the
        # ambulance dashboard shows — one source of truth on the server.
        de = a.get("dest_eta_sec")
        dd = a.get("dest_distance_m")
        eta_min = max(1, round(de / 60.0)) if de is not None else None
        dist_km = round(dd / 1000.0, 1) if dd is not None else None
        tgt = a.get("target") or {}
        phase = "responding" if tgt.get("kind") == "scene" else "inbound"
        out.append({
            "unit": a.get("id"), "trip_id": a.get("trip_id"), "condition": a.get("cls"),
            "trip_type": a.get("trip_type"), "leg": a.get("leg"), "phase": phase,
            "house_call": a.get("trip_type") == "HOUSE_CALL",
            "eta_min": eta_min, "dist_km": dist_km, "speed_kph": a.get("speed_kph"),
            "has_fix": has_fix, "stale": a.get("stale", False),
        })
    out.sort(key=lambda x: (0 if x["condition"] == "code_red" else 1,
                            x["eta_min"] if x["eta_min"] is not None else 1e9))
    return out


import time as _time
_cases: dict = {}   # hospital_id -> {trip_id -> case}; rolling in-memory case log (demo-grade)


def _hospital_history_stats(hid, inbound, snap):
    """Maintain a rolling case log for this hospital and compute dashboard stats.
    A case is recorded/refreshed while a unit is inbound; when it drops out of the
    inbound set it is marked 'arrived'. In-memory only (resets on restart)."""
    now = _time.time()
    log = _cases.setdefault(hid, {})
    seen = set()
    for it in inbound:
        tid = it.get("trip_id") or it.get("unit")
        seen.add(tid)
        c = log.get(tid) or {"unit": it.get("unit"), "first_ts": now}
        c["unit"] = it.get("unit"); c["condition"] = it.get("condition")
        c["house_call"] = it.get("house_call"); c["last_ts"] = now
        c["status"] = "responding" if it.get("phase") == "responding" else "inbound"
        log[tid] = c
    for tid, c in log.items():
        if tid not in seen and c.get("status") in ("inbound", "responding"):
            c["status"] = "arrived"; c["last_ts"] = now
    if len(log) > 40:
        keep = {tid for tid, _ in sorted(log.items(), key=lambda kv: kv[1].get("last_ts", 0), reverse=True)[:40]}
        for tid in [t for t in log if t not in keep]:
            log.pop(tid, None)
    ordered = [c for _, c in sorted(log.items(), key=lambda kv: kv[1].get("last_ts", 0), reverse=True)]
    hist = [{"unit": c["unit"], "condition": c.get("condition"), "house_call": c.get("house_call", False),
             "status": c.get("status", "inbound"),
             "time": _time.strftime("%H:%M", _time.localtime(c.get("first_ts", now)))} for c in ordered[:12]]
    red = sum(1 for it in inbound if it.get("condition") == "code_red")
    blue = sum(1 for it in inbound if it.get("condition") == "code_blue")
    etas = [it["eta_min"] for it in inbound if it.get("eta_min") is not None and it.get("phase") != "responding"]
    today = _time.strftime("%Y-%m-%d")
    cases_today = sum(1 for c in log.values()
                      if _time.strftime("%Y-%m-%d", _time.localtime(c.get("first_ts", now))) == today)
    stats = {"inbound": len(inbound), "red": red, "blue": blue,
             "avg_eta_min": (round(sum(etas) / len(etas)) if etas else None),
             "cases_today": cases_today,
             "active_units_total": sum(1 for a in snap.get("ambulances", []) if a.get("active"))}
    return hist, stats


@api.get("/hospital")
async def hospital_page():
    return FileResponse(__file__.replace("app.py", "hospital.html"))


@api.get("/hospitals")
async def hospitals_list():
    return JSONResponse({"hospitals": hospitals.list_with_beds()})


@api.get("/hospital/state")
async def hospital_state(id: str = ""):
    h = hospitals.get(id)
    if not h:
        return JSONResponse({"error": "unknown hospital", "hospital": None,
                             "inbound": [], "beds": None}, status_code=404)
    snap = engine.snapshot()
    inbound = _inbound_for(h, snap)
    history, stats = _hospital_history_stats(id, inbound, snap)
    return JSONResponse({"hospital": h, "beds": hospitals.beds(id),
                         "inbound": inbound, "history": history, "stats": stats,
                         "tick": snap.get("tick"), "online": snap.get("online")})


@api.post("/hospital/beds")
async def hospital_beds(request: Request):
    d = await request.json()
    hid = d.get("id")
    if not hospitals.get(hid):
        return JSONResponse({"error": "unknown hospital"}, status_code=404)
    b = hospitals.set_beds(hid, beds_available=d.get("beds_available"), beds_total=d.get("beds_total"),
                           icu_available=d.get("icu_available"), ed_open=d.get("ed_open"), note=d.get("note"))
    engine._log("beds_update", "hospital", hid, f"avail={b.get('beds_available')} ed_open={b.get('ed_open')}")
    return JSONResponse({"ok": True, "beds": b})


def _ws_authed(ws, provided: str) -> bool:
    """Authorize an ops CONTROL connection. If OPS_TOKEN is set it is REQUIRED;
    if it is unset, only localhost may control (secure-by-default for remotes)."""
    if _ops_token:
        return provided == _ops_token
    host = ws.client.host if ws.client else ""
    return host in ("127.0.0.1", "::1", "localhost")


def _apply_ops_command(msg: dict, authed: bool) -> None:
    t = msg.get("type")
    if t in CONTROL_CMDS and not authed:
        engine._log("ops_reject", "ws", "", f"unauthenticated {t}")
        return
    if t == "kill_server":
        engine.online = False
        engine._log("kill_server", "ops", "", "renewals stopped")
    elif t == "restore":
        engine.online = True
        engine._log("restore", "ops", "", "")
    elif t == "monitor_reset":
        jid = msg.get("junction")
        if jid in engine.monitors:
            engine.monitors[jid].external_reset()
            engine._log("monitor_reset", "ops", jid, "external reset")
    elif t == "close_incident":
        iid = msg.get("incident")
        if iid:
            engine.close_incident(iid)
            engine._log("close_incident", "ops", "", iid)


@api.websocket("/ws")
async def ops_ws(ws: WebSocket):
    await ws.accept()
    ops_clients.add(ws)
    # broadcast (read) stays open; CONTROL commands require auth (token or localhost)
    authed = _ws_authed(ws, ws.query_params.get("token", ""))
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("type") == "auth":
                authed = _ws_authed(ws, msg.get("token", ""))
                await ws.send_text(json.dumps({"type": "auth_result", "ok": authed}))
                continue
            _apply_ops_command(msg, authed)
    except WebSocketDisconnect:
        pass
    finally:
        ops_clients.discard(ws)


# ---------------- background loops ----------------
async def _engine_loop():
    dt = cfg.timings.tick_ms / 1000
    while True:
        engine.tick(dt)
        await asyncio.sleep(dt)


async def _broadcast_loop():
    while True:
        snap = engine.snapshot()
        dead = []
        for ws in ops_clients:
            try:
                await ws.send_text(json.dumps(snap))
            except Exception:
                dead.append(ws)
        for ws in dead:
            ops_clients.discard(ws)
        for dev, sid in list(device_sids.items()):
            c = engine.corridor_for(dev)
            if c:
                try:
                    await sio.emit("corridor:update", c, to=sid)
                except Exception:
                    pass
        await asyncio.sleep(0.5)


async def _route_loop():
    """Off the safety tick: for each authorized unit with a fix + destination,
    derive the corridor from the road route's traffic signals (OSRM + OSM) and
    feed it to the engine as virtual junctions. Rebuilt only when the destination
    changes or the unit drifts ROUTE_MOVE_M. Network I/O runs in a worker thread.

    Gated by LIVE_CORRIDOR while the map UIs are being updated to render the
    dynamic (virtual) junctions — off by default keeps the fixed-junction view."""
    if os.getenv("LIVE_CORRIDOR", "0").lower() not in ("1", "true", "yes", "on"):
        engine._log("route", "system", "", "LIVE_CORRIDOR off — dynamic corridor disabled")
        return
    while True:
        for uid, a in list(engine.ambulances.items()):
            # leg 1 = respond to the ACCIDENT (scene); leg 2 = transport to hospital.
            # The route (and therefore the ops map) follows the current leg's target.
            if a.leg == 1 and a.scene_lat is not None and a.scene_lng is not None:
                tgt_lat, tgt_lng, tgt_kind = a.scene_lat, a.scene_lng, "scene"
            else:
                tgt_lat, tgt_lng, tgt_kind = a.dest_lat, a.dest_lng, "dest"
            authorized = a.has_fix and engine._active(a) and tgt_lat is not None and tgt_lng is not None
            if not authorized:
                engine.clear_route(uid)
                _route_anchor.pop(uid, None)
                continue
            key = (tgt_kind, round(tgt_lat, 5), round(tgt_lng, 5))
            prev = _route_anchor.get(uid)
            moved = topology.haversine_m(a.lat, a.lng, prev[1], prev[2]) if prev else 1e9
            if prev and prev[0] == key and moved < ROUTE_MOVE_M:
                continue  # route still fresh
            try:
                signals, path = await live_signals.route_and_signals(a.lat, a.lng, tgt_lat, tgt_lng)
                engine.set_route(uid, signals, path)
                _route_anchor[uid] = (key, a.lat, a.lng)
                engine._log("route", uid, "", f"{len(signals)} signals on route → {tgt_kind}")
            except Exception as ex:  # noqa: BLE001 — network/route failure is non-fatal
                engine._log("route_err", uid, "", str(ex)[:48])
        await asyncio.sleep(ROUTE_REFRESH_S)


@api.on_event("startup")
async def _startup():
    asyncio.create_task(_engine_loop())
    asyncio.create_task(_broadcast_loop())
    asyncio.create_task(_route_loop())
