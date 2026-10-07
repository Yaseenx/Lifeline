# Ambulance Unit

The in-vehicle half of the Smart Ambulance Green-Corridor System. It is **two
coordinated programs** that run on the Raspberry Pi 4 in the ambulance:

```
   ┌──────────────────────────────────────────────────────────────────┐
   │  RASPBERRY PI 4 (in the ambulance)                                 │
   │                                                                    │
   │   ┌────────────────────┐   ws://localhost:8765   ┌──────────────┐  │
   │   │   DASHBOARD (React) │◀───── state ──────────▶│              │  │
   │   │   touchscreen UI    │────── commands ───────▶│  AGENT       │  │
   │   └────────────────────┘                         │  (Python)    │  │
   │                                                   │              │  │
   │                              NEO-M8N GPS ────────▶│  • GPS read  │  │
   │                                                   │  • cloud link│  │
   │                                                   │  • auth/sign │  │
   │                                                   └──────┬───────┘  │
   └─────────────────────────────────────────────────────────│──────────┘
                                                               │ 4G, Socket.IO
                                                               │ (authenticated)
                                                      ┌────────▼─────────┐
                                                      │  CENTRAL SERVER  │
                                                      │  (separate unit) │
                                                      └──────────────────┘
```

**Why the split?** The agent owns the hardware (GPS), the 4G link, and the signed
device credential. The dashboard talks **only** to the agent over localhost, so the
browser never holds cloud credentials and the UI keeps working across reconnects.

> The agent is purely a *vehicle client*: it reports position and trip state and
> displays what the server sends back. It does **not** control any traffic signal —
> all corridor and fail-safe logic lives in the server and at the junctions.

---

## Layout

```
ambulance-unit/
├── agent/                  Python device agent (runs on the Pi)
│   ├── main.py             orchestration / main loop
│   ├── config.py           env-driven config
│   ├── protocol.py         event names + message types (mirror of dashboard)
│   ├── state.py            VehicleState model
│   ├── auth.py             device credential signing  (HMAC dev → asymmetric prod)
│   ├── gps.py              SimulatedGps + SerialGps (NEO-M8N)
│   ├── cloud_client.py     authenticated Socket.IO link to the server
│   ├── ui_bridge.py        localhost websocket for the dashboard
│   ├── requirements.txt
│   └── .env.example
├── dashboard/              React + Google Maps touchscreen UI (runs on the Pi)
│   └── src/
│       ├── App.tsx
│       ├── protocol.ts     message types (mirror of agent/protocol.py)
│       ├── hooks/          useAgentSocket, useSimulatedVehicle, useDeviceVehicle
│       └── components/     MapView, SosPanel, StatusBar, CorridorPanel, HazardBanner, …
└── tools/
    └── mock_server.py      DEV-ONLY fake server to demo the full loop
```

> Note (2026-07-03): moved here from `~/Downloads/ser`. `package-lock.json` was not
> carried over — run `npm install` in `dashboard/` to regenerate it and
> `node_modules/`.

## Trip model — added 2026-07-03

Trips are `trip_type × emergency × leg`: **SCENE** (emergency at a scene),
**HOUSE_CALL** (two legs — 1: to the residence, 2: to hospital, flipped by the
*Patient onboard* button; emergency or not), **TRANSFER** (non-emergency
transport). **Hard rule:** a non-emergency trip *never* requests preemption —
the agent emits `vehicle:sos` only when `emergency=true`, and refuses any
corridor pushed at it otherwise (see `_on_corridor`). Escalate (with condition)
and de-escalate (releases the corridor immediately) flip a live trip either
way. New commands: `start_trip`, `end_trip`, `patient_onboard`, `escalate`,
`deescalate` (`sos` kept as the emergency-scene shortcut).

## Grant semantics (MON-8 / SEC-10) — added 2026-07-03

The corridor panel shows an explicit per-junction grant state from the server:
`granted` (junction cleared for this vehicle) vs `queued` / `requested` /
`rejected` / `red` (**obey the signals**). The driver must never assume
right-of-way from a missing or ambiguous state — only an explicit `granted`
renders green. Node states pass through the agent untouched, so this is purely
a server→UI contract: the corridor server sends
`nodes[].state ∈ {idle, requested, queued, granted, green, rejected, red, passed}`.

---

## Run it on a laptop (no hardware, no real server)

Three terminals. Everything defaults to simulation, so it works out of the box.

**1 — dev mock server** (fabricates a corridor when you hit SOS):
```bash
cd ambulance-unit
python -m venv .venv && source .venv/bin/activate
pip install -r agent/requirements.txt
python tools/mock_server.py            # listens on :4000
```

**2 — the agent** (simulated GPS by default):
```bash
cd ambulance-unit
source .venv/bin/activate
cp agent/.env.example agent/.env       # optional; defaults are fine
cd agent && python main.py
```

**3 — the dashboard:**
```bash
cd ambulance-unit/dashboard
npm install
cp .env.example .env                   # optional; defaults to ws://localhost:8765
npm run dev                            # open the printed http://localhost:5173
```

You should see the ambulance moving along the simulated route. Tap **Start
emergency** and the mock server streams back a corridor (nodes turn green) plus a
sample hazard banner. Without the mock server the agent still runs and the map still
moves — the corridor panel just stays idle.

---

## Moving to real hardware

- **GPS (NEO-M8N):** set `GPS_MODE=serial` and `GPS_SERIAL_PORT=/dev/serial0` in
  `agent/.env`. Enable the Pi UART (`raspi-config` → Interface → Serial: login shell
  off, hardware serial on). `pyserial` + `pynmea2` are already in requirements.
- **Real server:** point `CLOUD_URL` at your central server. The agent speaks the
  events in `agent/protocol.py`; implement the matching handlers server-side.
- **Auth:** the dev build signs with a shared HMAC secret. For production, provision
  a unique asymmetric key per vehicle and verify signatures server-side. The `Auth`
  interface stays the same.
- **Hospital list:** currently hardcoded in `SosPanel.tsx`. Serve it from the agent
  or central server and load it on startup.
- **Kiosk:** run the dashboard build (`npm run build` → `npm run preview`) in a
  full-screen Chromium kiosk on the Pi's touchscreen.

---

## Safety / UX notes baked in

- **Don't type while driving.** Destination/condition are taps, and trips should be
  auto-populated from dispatch where possible. *(TODO: voice entry for mid-route
  changes; dispatch integration to pre-fill the trip.)*
- **Default condition.** If SOS is active and no condition is chosen within
  `CONDITION_TIMEOUT_SEC` (10s), the agent applies `DEFAULT_CONDITION`.
- **Connection honesty.** The status bar shows unit / server / GPS health separately
  so the driver always knows what is live.
- **Explicit grant only.** The grant banner never shows "cleared" unless the server
  explicitly granted the next junction; everything else says "obey signals".
- **Glanceable design.** Dark, high-contrast theme, large SOS button, big touch
  targets, tabular ETA numerals — readable at speed and in sunlight.

---

## TODO checklist

- [ ] Voice entry for hands-free destination/condition changes
- [ ] Dispatch (108 / GVK-EMRI) integration to auto-create trips
- [x] ~~Add search/nearest hospitals~~ — live OSM fetch of every mapped hospital near the GPS (`hospitalsLive.ts` + `useNearbyHospitals`), merged with the curated verified list, nearest-first (2026-07-03)
- [ ] Serve the *verified/empanelled* hospital registry from the server (108/EMRI + TN Health data) — replaces the curated list as the trusted tier
- [ ] Asymmetric per-device auth + provisioning flow
- [ ] Render server `route:suggest` reroutes with an accept/decline prompt
- [ ] Audible alert for critical hazards (tie to the junction hooter timing)
- [ ] Offline tile cache for the corridor area
- [ ] systemd units to auto-start agent + kiosk on boot
