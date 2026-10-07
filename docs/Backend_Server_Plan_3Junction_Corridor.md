# Backend & Server Plan — 3-Junction Green-Corridor

Central server that powers the three-junction corridor frontend (J1 — J2 — J3, linked by gap roads). It ingests ambulance SOS + live position, decides signal preemption across all three junctions, streams signal/lease state back to the frontend and (later) to real edge controllers, and enforces the safety rules. This document is the spec to hand to the frontend-integration chat.

---

## 1. Assumptions (change any of these and the plan flexes)

- **Stack:** Python 3.11 + FastAPI + native WebSocket, `asyncio` tick loop. Matches the existing repo (the agent code and `sim_server.py` are already Python). Node/Express + `ws` is a drop-in alternative if preferred.
- **Authority:** the **server is authoritative for control logic** (signal states, leases, arbitration). The frontend renders server state and sends user actions + ambulance telemetry. The frontend must still run standalone (offline flag) so the visual isn't hard-blocked on the server.
- **State:** in-memory dataclasses for the demo; Redis optional later for lease sharing across workers; SQLite/Postgres for the audit log + config.
- **Scope now:** drive the simulation and reproduce C1–C12. Written so the same command path can later drive real controllers (Mode A = request into existing controller; Mode B = drive lamps under an independent conflict monitor).

---

## 2. Architecture

```
 ┌───────────────┐     WebSocket (JSON, HMAC-signed)     ┌──────────────────────────┐
 │  Frontend sim │  ◄──────────────────────────────────► │  Realtime Gateway (WS)   │
 │ (3 junctions) │   dispatch / telemetry / kill          │  FastAPI + uvicorn       │
 └───────────────┘   ◄ junctions / leases / commands      └────────────┬─────────────┘
 ┌───────────────┐                                                     │
 │ Ambulance     │  ── SOS / telemetry ──►                             ▼
 │ agent (later) │                                         ┌──────────────────────────┐
 └───────────────┘                                         │  Engine (10 Hz tick)     │
                                                           │  ├─ Telemetry ingest      │
                                                           │  ├─ Arbiter (priority,    │
                                                           │  │   lease, writer epoch) │
                                                           │  ├─ Per-junction FSM      │
                                                           │  ├─ Corridor coordinator  │
                                                           │  └─ Safety / monitor      │
                                                           └───────┬─────────┬─────────┘
                                                          Security  │         │  Audit (hash-chained)
                                                        (HMAC/nonce) │         │
```

Core services:

- **Realtime Gateway** — WebSocket + a few REST endpoints (health, config, audit export). One socket per client.
- **Engine** — fixed-rate authoritative loop (100 ms). Every tick: ingest telemetry, run the arbiter, advance each junction's state machine, run the corridor coordinator, apply safety overrides, broadcast state, append audit.
- **Arbiter** — cross-junction priority + lease management + single-writer fencing.
- **Per-junction controller FSM** — normal cycle + preemption + min-green + clearance + monitor. One instance per junction (J1, J2, J3), independent.
- **Corridor coordinator** — sequences preemption along the corridor (the green wave) using link travel time as the offset; handles rolling hand-off.
- **Safety** — lease TTL fail-safe, conflict-monitor trip, comms-lost revert, Mode-A reject.
- **Security** — HMAC signing, nonce replay cache, freshness window.
- **Audit** — hash-chained event log.

---

## 3. Topology & data model

The corridor is data, not hard-coded, so the same server handles 1 or N junctions.

```yaml
# config.yaml
corridor:
  junctions: [J1, J2, J3]        # ordered along the corridor
  links:                          # the gap roads
    - {from: J1, to: J2, length_m: 600, freeflow_mps: 12}
    - {from: J2, to: J3, length_m: 600, freeflow_mps: 12}
timings:
  green_s: 9
  amber_s: 2
  allred_s: 1.5
  min_green_s: 4
  lead_m: 450          # preempt when ambulance is within this of the stop line
  lease_ttl_ms: 1500   # edge reverts if not renewed within this
  renew_ms: 500
  tick_ms: 100
```

Entities:

- **Junction** `{id, ns:phase, ew:phase, green_age, mode: normal|preempt|flash|manual, owner: lease?, writer_epoch}` where `phase ∈ {green, amber, red, off}`.
- **Link** `{from, to, length_m, freeflow_mps}` — the gap road; its travel time sets the green-wave offset.
- **Ambulance** `{id, code: red|blue, sos_ts, route: [ {junction, movement} ], pos: {link|junction, offset_m}, speed_mps, status}`.
- **Lease** `{junction, ambulance_id, epoch, granted_at, ttl_ms, renew_by}` — a junction is preempted only while it holds a live lease; expiry = automatic revert (the fail-safe).

---

## 4. Integration contract (hand this to the frontend chat)

WebSocket at `ws://<host>:8000/ws`. Every message is an envelope:

```json
{ "payload": { ... }, "ts": 1730000000.123, "nonce": "9f2a…", "sig": "hex-hmac" }
```

**Client → Server**

| type | payload | when |
|---|---|---|
| `hello` | `{role:"frontend"|"agent", clientId}` | on connect |
| `dispatch` | `{ambId?, entry:"J1", dir:"EB", code:"red"|"blue"}` | user hits Dispatch |
| `telemetry` | `{ambId, link|junction, offset_m, speed_mps, code, sos_ts}` | each frontend tick (if frontend simulates motion) |
| `scenario` | `{id:"C1".."C12"}` | optional, to stage a case |
| `kill_server` / `restore` | `{}` | fail-safe demo |

**Server → Client** (broadcast every tick)

| type | payload |
|---|---|
| `topology` | junctions + links + corridor order (sent once on hello) |
| `junctions` | `[{id, ns, ew, mode, owner:ambId?, green_age}]` |
| `leases` | `[{junction, ambId, ttl_left_ms}]` |
| `ambulances` | `[{id, pos, speed, code, status, next_junction, eta_s}]` (server-authoritative) |
| `commands` | audit stream `[{ts, junction, cmd:"GREEN|AMBER|ALLRED|REVERT|FLASH", ambId, reason}]` |
| `server_status` | `{online, tick, mode}` |

Two integration modes (pick per client via `hello`):

- **Server-authoritative** (recommended): frontend sends `dispatch`/`scenario`, renders `junctions`+`ambulances`. Deterministic, easiest to reproduce C1–C12.
- **Frontend-sim + server-control**: frontend simulates ambulance motion and streams `telemetry`; server returns `junctions`/`commands`; frontend renders its own vehicles. Closer to reality (ambulance = sensor).

---

## 5. Control logic (server side)

Per-junction FSM (mirrors the working single-junction frontend, moved to the server):

```
normal cycle  →  [preempt request]  →  select
select:  target green?           → hold
         other green & age<MIN   → hold min-green, then clearA
         other green & age≥MIN   → clearA
         all red                 → hold
clearA (amber other)  → clearR (all-red)  → hold (target green, corridor)
hold: target ambulances cleared?  → other pending? postA→postR→switch : resume
resume (all-red)  → normal
monitor trip → flashing red (overrides all) → normal
```

Arbiter (each tick, per junction over ambulances within `lead_m`): sort by **class (Code Red > Code Blue) → SOS timestamp → id**; the winner requests/holds the lease. **Single-writer fencing:** each grant carries a monotonically increasing `writer_epoch`; an edge ignores any command with an epoch lower than the last it accepted (prevents split-brain).

Corridor coordinator (the new three-junction piece): when an ambulance is committed to the corridor, schedule preemption of the **next** junction to turn green `link_length / speed` seconds before arrival (the offset), so greens roll ahead of it. Release each junction as soon as the ambulance clears it (lease expiry / `cleared` flag) — that's the rolling hand-off.

Safety: lease TTL means if the server/comms drop, junctions revert on their own clock (no stuck greens); conflict-monitor trip forces one junction to flashing red without touching the others; min-green blocks unsafe instant flips; Mode-A reject flag lets a junction decline preemption and keep normal timing.

---

## 6. C1–C12 → backend feature map

| Case | Backend feature exercised |
|---|---|
| C1 Green wave | coordinator offsets, sequential preempt J1→J2→J3 |
| C2 Rolling hand-off | lease release on `cleared`, per-junction independence |
| C3 Platoon | multiple leases same direction, lease renew/extend |
| C4 Opposing corridor | compatible-movement grant (both through), shared green |
| C5 Cross vs corridor at J2 | arbiter at one junction, others untouched |
| C6 Convergence at J2 | arbiter + clearance (amber+all-red) sequencing |
| C7 Red interrupts Blue wave | class-priority preemption, wave break + resume |
| C8 Two simultaneous preempts | independent FSMs, arbiter per junction, coordinator |
| C9 Comms lost | lease TTL expiry → auto revert (fail-safe) |
| C10 Monitor trip at J2 | monitor override → flashing red, scoped to J2 |
| C11 Min-green hold | FSM min-green gate before switching |
| C12 Mode-A reject | per-junction reject flag → normal timing |

Ship `scenarios.py` that stages each case (positions, codes, SOS times, flags) so the test suite and the frontend selector both trigger identical setups.

---

## 7. Security & audit

- **HMAC-SHA256** signature over `{payload, ts, nonce}` with a per-device shared secret; verify on every inbound message.
- **Replay protection:** reject if `ts` outside a ±2 s freshness window, or if `nonce` already seen (short-lived cache). `ambId+sos_ts` gives trip idempotency.
- **Audit:** append-only, hash-chained (`h_n = H(h_{n-1} + event)`) so tampering is detectable; export via REST. Log every grant/revert/override with reason.
- Secrets from env/`.env` only (no secrets in the repo; keep the dev placeholder out of commits).

---

## 8. Project structure

```
server/
  app.py            # FastAPI app, WS + REST routes, broadcast fan-out
  contracts.py      # Pydantic models = the §4 message contract
  topology.py       # load config.yaml → junctions, links, corridor
  controller.py     # per-junction FSM (normal + preempt + min-green + clearance + monitor)
  arbiter.py        # priority sort + lease grant/renew/expire + writer epoch
  coordinator.py    # corridor green-wave offsets + rolling hand-off
  engine.py         # 10 Hz tick: ingest → arbiter → controllers → coordinator → safety → broadcast
  security.py       # HMAC sign/verify, nonce cache, freshness window
  audit.py          # hash-chained event log + export
  scenarios.py      # C1..C12 staged setups
  config.yaml       # timings, topology, link lengths
tests/
  test_arbiter.py  test_controller.py  test_coordinator.py
  test_safety.py   test_contract.py    test_scenarios_c1_c12.py
run.md              # how to start server + point the frontend at it
```

---

## 9. Build phases (each independently testable)

1. **Skeleton + contract** — FastAPI, WS gateway, Pydantic models, `topology.py`, broadcast a dummy tick. Frontend can connect and see `topology`/`junctions`.
2. **Per-junction FSM** — normal cycle + preempt + min-green + clearance. Reach parity with the current single-junction sim for one junction.
3. **Arbiter + leases + writer epoch** — priority, lease lifecycle, fencing.
4. **Corridor coordinator** — offsets + rolling hand-off → C1–C4.
5. **Cross-conflicts + contention** → C5–C8.
6. **Safety** — lease TTL, monitor trip, comms lost, Mode-A reject → C9–C12.
7. **Security + audit** — HMAC/nonce/freshness, hash-chained log.
8. **Test suite** — deterministic tick, assert lamp sequences + invariants for C1–C12.
9. **Package** — Dockerfile / `docker-compose` (api [+ redis + postgres]) + `run.md`.

---

## 10. Test suite (definition of done)

Run the engine headless with a fixed dt; for each case assert: correct grant order, no conflicting greens ever (`not (ns==green and ew==green)` at any junction), clearance served before every switch, min-green respected, lease expiry reverts within `ttl`, monitor trip scoped to one junction, coordinator offsets keep the ambulance non-stop on C1. These mirror the SAFE-invariants already in the repo test suite.

---

## 11. Handoff notes for the frontend chat

- Point the existing 3-junction frontend at `ws://localhost:8000/ws`; on connect send `hello{role:"frontend"}`, then render `junctions` (lamp states), `ambulances` (markers), and feed `commands`/`leases`/`server_status` into the server module panel.
- Map the frontend's three junctions to topology ids `J1/J2/J3`; the gap-road lengths in `config.yaml` set the green-wave timing.
- Wire the Dispatch button → `dispatch{entry, dir, code}`; the (optional) case selector → `scenario{id}`; Kill-server → `kill_server` and watch leases expire → everything reverts.
- Keep an offline flag so the frontend still animates if the socket is down.
