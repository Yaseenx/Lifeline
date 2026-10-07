#!/usr/bin/env python3
"""
BENCH TEST TOOL — not part of the deployed system.

Feeds a REAL Chennai route along the pilot corridor to the on-device agent over
its UI bridge, exactly as a phone's browser geolocation would (the `gps_fix`
command). Use it for a desk dry-run when you don't have a phone/GPS in the
vehicle. The agent still signs and relays real telemetry to the server; only the
SOURCE of movement is replayed here — nothing about the server/dispatch/signal
path is faked.

Prereq: the agent is running with GPS_MODE=phone and connected to the server.
Run:    python3 tools/route_player.py         (default: J1->J2->J3, ~43 km/h)
        SPEED_KPH=25 python3 tools/route_player.py

Demo sequence:
  1) start server, start agent (it registers as an AVAILABLE unit)
  2) start this player  -> the unit appears and HOLDS at the start for a few
     seconds (START_HOLD_S) so you can dispatch
  3) in /console, dispatch an incident near the corridor -> this (nearest) unit
     is assigned; as it drives, J1/J2/J3 preempt on the ops map + LEDs.
"""
import asyncio
import json
import math
import os

UI_URL = os.getenv("AGENT_UI_URL", "ws://127.0.0.1:8765")
SPEED_MPS = float(os.getenv("SPEED_KPH", "43")) / 3.6
HZ = float(os.getenv("GPS_HZ", "2"))

# EVR Periyar Salai pilot corridor: ~650 m east of J1 -> J1 MMC -> J2 Vepery ->
# J3 Kilpauk MC -> a little past, so all three junctions are engaged in order.
ROUTE = [
    (13.0809, 80.2817),
    (13.0809, 80.2757),   # J1 MMC / RGGGH
    (13.0827, 80.2620),   # J2 Vepery
    (13.0790, 80.2445),   # J3 Kilpauk MC
    (13.0790, 80.2405),
]


def _dist(a, b):
    R = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _bearing(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dl = lo2 - lo1
    y = math.sin(dl) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


async def main():
    import websockets
    step = max(1.0, SPEED_MPS / HZ)
    async def drain(ws):
        try:
            async for _ in ws:
                pass
        except Exception:
            pass

    async with websockets.connect(UI_URL) as ws:
        asyncio.create_task(drain(ws))
        print(f"connected to agent UI bridge {UI_URL}; streaming route (Ctrl-C to stop)")
        # Hold at the start so the unit registers and you have time to dispatch
        # in /console before it starts moving.
        hdg0 = _bearing(ROUTE[0], ROUTE[1])
        hold = float(os.getenv("START_HOLD_S", "8"))
        held = 0.0
        while held < hold:
            await ws.send(json.dumps({"type": "command", "action": "gps_fix",
                "payload": {"lat": ROUTE[0][0], "lng": ROUTE[0][1],
                            "speed_kph": 0, "heading_deg": hdg0}}))
            await asyncio.sleep(1.0 / HZ)
            held += 1.0 / HZ
        print(f"held {hold:.0f}s at start — dispatch now in /console; now driving the corridor…")
        for i in range(len(ROUTE) - 1):
            a, b = ROUTE[i], ROUTE[i + 1]
            seg, hdg = _dist(a, b), _bearing(a, b)
            n = max(1, int(seg / step))
            for s in range(n):
                t = s / n
                lat = a[0] + (b[0] - a[0]) * t
                lng = a[1] + (b[1] - a[1]) * t
                await ws.send(json.dumps({"type": "command", "action": "gps_fix",
                    "payload": {"lat": lat, "lng": lng,
                                "speed_kph": SPEED_MPS * 3.6, "heading_deg": hdg}}))
                await asyncio.sleep(1.0 / HZ)
        print("route complete — unit is past J3")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
