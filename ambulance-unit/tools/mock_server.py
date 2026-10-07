"""DEV/TEST ONLY mock central server.

Accepts the agent's authenticated connection and, when SOS goes active, streams back
a fabricated corridor (and one hazard) so you can exercise the dashboard end-to-end
without the real backend. NOT part of the ambulance unit and NOT for production.

Run:  python tools/mock_server.py   (listens on :4000)
"""
import asyncio
from aiohttp import web
import socketio

sio = socketio.AsyncServer(cors_allowed_origins="*", async_mode="aiohttp")
app = web.Application()
sio.attach(app)


@sio.event
async def connect(sid, environ, auth):
    print("agent connected:", sid, "| auth present:", bool(auth))


@sio.on("vehicle:telemetry")
async def on_tel(sid, data):
    pass  # print(data) to watch position


@sio.on("vehicle:trip")
async def on_trip(sid, data):
    print(f"TRIP: type={data.get('trip_type')} emergency={data.get('emergency')} "
          f"leg={data.get('leg')} onboard={data.get('patient_onboard')} -> {data}")


@sio.on("vehicle:sos")
async def on_sos(sid, data):
    # The agent only emits sos for EMERGENCY trips (non-emergency never
    # preempts) — so a corridor is only ever streamed from here.
    print("SOS:", data)
    if data.get("active"):
        asyncio.create_task(stream_corridor(sid, data))


async def stream_corridor(sid, sos):
    base = (13.0827, 80.2707)
    nodes = [
        {"id": f"N{i}", "name": f"Signal {i}",
         "lat": base[0] + 0.004 * i, "lng": base[1] + 0.003 * i,
         "state": "idle", "eta_sec": 20 * i}
        for i in range(1, 5)
    ]
    await sio.emit("trip:ack", {"trip_id": sos.get("trip_id"), "accepted": True}, to=sid)
    for step in range(8):
        # Exercise the explicit grant semantics (MON-8/SEC-10): the node the
        # vehicle approaches is GRANTED, later ones are QUEUED, passed ones PASSED.
        cur = step % len(nodes)
        for i, n in enumerate(nodes):
            n["state"] = "passed" if i < cur else ("granted" if i == cur else "queued")
            n["eta_sec"] = max(0, (n["eta_sec"] or 0) - 5)
        await sio.emit("corridor:update", {
            "status": "active", "trip_id": sos.get("trip_id"),
            "queue_position": 1, "safe_speed_kph": 38, "nodes": nodes}, to=sid)
        if step == 2:
            await sio.emit("hazard:alert", {
                "node_id": "N2", "type": "pedestrian",
                "message": "Pedestrian near crossing", "severity": "warn", "lane": "2"}, to=sid)
        await asyncio.sleep(3)


if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=4000)
