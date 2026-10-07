# LifeLine — Deployment & Run Runbook

How to run the **real** system end to end. No simulators, no placeholders (fire
is a scaffold, off by default). Everything below is the production code path; the
only things you supply are Meta WhatsApp credentials and the Raspberry Pi + LED
hardware.

## The pieces

| Component | Where it runs | File(s) |
|-----------|---------------|---------|
| Corridor server | a laptop / VM (the control centre) | `server/app.py` + engine/arbiter/monitor/dispatch/coordinator/intake |
| Call-taker console | browser → server | `server/console.html` (`/console`) |
| Ops map | browser → server | `server/ops.html` (`/`) |
| Ambulance agent | a device in the vehicle (Pi or laptop) | `ambulance-unit/agent/` |
| Driver dashboard | a **phone** in the vehicle (provides GPS) | `ambulance-unit/dashboard/` |
| Signal node (×3) | one Raspberry Pi per junction + LEDs | `server/edge_signal.py` + `server/gpio_driver.py` |

Flow: **call-taker types the address → server geocodes + dispatches the nearest
ambulance → that ambulance’s phone GPS streams through the agent → the server
clears its corridor junctions as it approaches → each junction’s Pi lights real
LEDs.** WhatsApp is a second intake channel.

---

## 1. Corridor server

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # fill in WhatsApp creds later (optional to start)
uvicorn app:app --host 0.0.0.0 --port 4000
```

Open **http://localhost:4000/console** (call-taker) and **http://localhost:4000/** (ops map).
`config.yaml` holds the 3 pilot junctions + timings + the per-device HMAC secret.

## 2. Ambulance agent (in the vehicle)

```bash
cd ambulance-unit/agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# edit .env: CLOUD_URL=http://<server-ip>:4000, DEVICE_ID/DEVICE_SECRET must
# match server/config.yaml, GPS_MODE=phone (default) or serial (NEO-M8N)
python3 main.py
```

- `GPS_MODE=phone` → the agent takes real GPS from the dashboard (below).
- `GPS_MODE=serial` → the agent reads a NEO-M8N on `GPS_SERIAL_PORT`.

## 3. Driver dashboard (the phone that provides GPS)

```bash
cd ambulance-unit/dashboard
npm install
# .env: VITE_AGENT_WS_URL=ws://<agent-ip>:8765 , VITE_GOOGLE_MAPS_API_KEY=...
npm run dev      # or: npm run build && npm run preview --host
```

Open the URL on a **phone in the ambulance** and allow location. The browser’s
GPS streams to the agent (`gps_fix`), which signs it and relays telemetry. When
the unit connects, it registers with the dispatcher as **available**.

## 4. Signal nodes — one Raspberry Pi per junction

Wire 6 LEDs per junction head (NS: R,A,G / EW: R,A,G) to BCM pins. Default map:
`ns={red:17,amber:27,green:22}, ew={red:23,amber:24,green:25}` (override with `PINS`).

```bash
# on each junction Pi:
pip install -r requirements-edge.txt      # websockets + gpiozero
SERVER_WS_URL=ws://<server-ip>:4000/ws JUNCTION_ID=J1 python3 edge_signal.py
```

Each Pi drives its own LEDs from the server feed and **flashes red on its own** if
the link drops (local watchdog) — no stuck greens even if the server dies.

## 5. WhatsApp intake (optional second channel)

Fill `server/.env` (`WA_ACCESS_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_VERIFY_TOKEN`),
expose the server (`ngrok http 4000`), and register `https://<tunnel>/wa/webhook`
in Meta with the verify token, subscribed to `messages`. A bystander then shares
their live location and gets an ambulance-dispatched reply. See the earlier
credential steps.

---

## Run a full dry-run (no hardware, no Meta needed)

1. Start the server. Open `/console` and `/`.
2. Start one agent (`DEVICE_ID=AMB-CHN-001`) and open the dashboard on a phone (or
   use `?live=1` in a browser to feed real laptop/phone GPS). It appears as an
   available unit.
3. In `/console`, type an accident address near the corridor, pick type/priority,
   Dispatch → the nearest ambulance is assigned.
4. As that unit’s GPS approaches the pilot junctions, watch `/` show them turn
   green ahead of it, then revert after it passes. If Pis are attached, their LEDs
   follow exactly.

## Provisioning a new vehicle

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# add  DEVICE_ID: <secret>  to server/config.yaml -> security.devices
# set the same DEVICE_ID/DEVICE_SECRET in that vehicle's agent .env
```

## Tests

```bash
cd <project root>
pip install pytest pyyaml
PYTHONPATH=server python3 -m pytest tests -q
```

Covers: the P2 safety-invariant fuzz (no conflicting greens, min-green, full
clearance, bounded holds), dispatch-driven corridor (incident-bound preemption,
Red>Blue, comms-loss TTL revert, monitor fault scoping), multi-channel intake
(call+geocode, WhatsApp), the edge node watchdog, and the fire scaffold guards.

## Safety notes (what keeps it safe)

- The per-junction FSM cannot express an unsafe transition (amber→green or
  sub-min-green raise); every green passes through full amber + all-red.
- An independent monitor watches commanded lamps and latches flash-red on any
  fault; only an operator reset clears it.
- Every grant is a lease with a short TTL — silence reverts the junction.
- Each signal Pi has its own watchdog (field-side dead-man).
- Preemption is incident-bound: only a dispatched unit gets a corridor.

## Not yet / do NOT do without approval

- Do **not** connect to a live city signal. These signal nodes drive your own
  LED model. Real signal control needs the hardware conflict monitor, NTCIP
  integration, a written safety case, and traffic-police/road-authority approval
  (see `Code_Review_Bulletproofing.md` and the production-grade checklist).
- WhatsApp temporary tokens last 24 h — use a permanent System User token for a
  standing deployment.
- Auth is per-device HMAC (dev-grade); production wants per-device asymmetric
  keys + mTLS, and an authenticated ops control plane.
