# Run the LifeLine corridor server

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --port 4000
```

- **Monitoring console:** open http://localhost:4000 — live dark map (Leaflet/
  OSM, no API key) with junction lamps (pulsing ring when owned, flashing on
  fault), ambulance positions with path trails, engagement lines
  (green=granted, amber dash=requested, grey dot=queued, red=rejected),
  contention alerts when several ambulances converge on one junction, junction
  and ambulance panels, and the live activity log. Buttons: demo Code Red/Blue
  dispatch, Kill server (watch leases expire and lamps revert — the C9
  fail-safe), fault drill + operator-only monitor reset.
- **Health:** `curl localhost:4000/health`
- **Tests:** `python -m pytest ../tests -q` (12 tests; the invariant fuzz is
  the P2 gate — it must always pass before anything else is added)

## Connect the ambulance unit

The server speaks the agent's existing protocol. In `ambulance-unit/agent/.env`
set `CLOUD_URL=http://localhost:4000` (already the default), then run the agent
and dashboard as usual. Start an emergency: approaching J1/J2/J3 (EVR corridor
coords in `config.yaml`) the corridor panel will show real
requested/queued/granted/passed states from the server, and the ops console
shows the same trip from the control-room side.

Device secrets live in `config.yaml` (`security.devices`) and must match the
agent's `DEVICE_ID`/`DEVICE_SECRET`. Unsigned, stale, replayed, or
unknown-device messages are rejected at ingress and logged.

## What is implemented (P0–P3) / what's next

Done: 10 Hz engine; per-junction FSM with inviolable clearance, min-green,
bounded holds; independent latching safety monitor (flash-red, operator-only
reset); arbiter with CODE_RED > CODE_BLUE, FCFS, bounded queue, writer-epoch
fencing; lease TTL auto-revert (comms-loss fail-safe); HMAC+freshness+replay
ingress; ops console; demo vehicles.

Next per BUILD_PLAN.md: P4 green-wave coordinator (ETA-based arming of the
NEXT junction, offsets), P5 contention cases C5–C8, P6 plausibility gating +
hash-chained audit + Chennai config matrix, P7 failure-mode fuzz + packaging.
