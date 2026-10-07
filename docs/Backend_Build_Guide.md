# Backend Build Guide — how to build the green-corridor server (safety-first)

This ties the two other docs together into a build order: the WebSocket/topology contract is in `Backend_Server_Plan_3Junction_Corridor.md`; the cited requirement IDs (ARB-/FSM-/CO-/MON-/SEC-/FAIL-) are in `Green_Corridor_Requirements_Catalog.md`. Read this for *how* to assemble it.

## The one big idea

A preemption request is **guilty until proven safe**. It flows through a pipeline of layers, and **each layer can only reduce authority, never add it** — authenticate → sanity-check → arbitrate → lease → coordinate → change the junction through mandatory safe intervals → and finally an **independent safety monitor** that watches the *commanded* output and can veto everything by forcing flash-red. Two more rules make it deployable: **everything is time-bounded** (a hold/lease expires and reverts on its own), and **the edge keeps final authority** (the server *requests*, the junction *disposes* — NTCIP 1211, ARB-5). If any layer is unsure, it drops to the safe state (fail-safe over obedience, SEC-9).

## The request-to-actuation pipeline (the heart of it)

Process every inbound request in this strict order. Rejection at any stage stops it cold.

1. **Ingress / auth** `[SEC-1,3,4]` — verify signature + certificate, timestamp inside the freshness window, not a replay (nonce/sequence cache). Drop unsigned/expired/replayed. (Reuse your existing `auth.py` HMAC+nonce and `sim_server.py` verify — that's exactly this layer.)
2. **Authorization / registry** `[SEC-2, ARB-7]` — is this vehicle in the authorized registry, and what is its *true* class/role? Class comes from the registry/cert, never from a message field.
3. **Plausibility gate** `[SEC-5,6]` — is the reported position on a known approach, speed/heading/accel consistent with the prior track, no teleport, message rate sane? GPS is spoofable for <$100, so never actuate on a single self-reported fix.
4. **Arbiter** `[ARB-1..8]` — rank rail > fire/EMS > police > light-rail > bus; first-come within a class; one owner per junction; a higher preempt overrides a lower; reservice throttle; **bounded queue** (survive request floods). Output: desired owner per junction + a monotonically increasing **writer epoch**.
5. **Lease manager** `[ARB, FSM-8]` — grant/renew/expire a lease with a short TTL. **Lease expiry = automatic revert** — this is the comms-loss fail-safe; a junction can never stay held because a "clear" message was lost or late.
6. **Corridor coordinator** `[CO-1..7]` — compute green-wave offsets (offset = link distance ÷ progression speed, minus queue clearance), arm the *next* junction by ETA look-ahead, share preempt status with neighbours, roll the hand-off (release behind the vehicle), refuse to discharge into a full downstream box, and plan the multi-cycle recovery.
7. **Per-junction state machine** `[FSM-1..10]` — the **only** thing that moves lamps. It receives a "desired state" and reaches it **only through mandatory safe intervals**: protect min-green, always run full yellow + all-red (never shorten/omit, never yellow→green on exit), hold if a vehicle is in the dilemma zone, honor the pedestrian-clearance floor, respect a minimum dwell, and auto-cancel on duration expiry.
8. **Independent safety monitor** `[MON-1..10]` — a **separate process** that watches the commanded outputs and trips to **flash-red, latched**, on any of: conflicting greens, dual indication, dark head, short/skipped clearance, or watchdog/heartbeat timeout. The corridor logic **cannot clear its own fault**. This is your software MMU; it is the reason a bug in layers 1–7 can't cause a collision.

Everything is logged (hash-chained audit, SEC-8) at each grant/deny with vehicle, class, time, junction, reason.

## Module map (files → what they own)

```
server/
  contracts.py     # SRM/SSM-style request+status messages (Plan §4 contract)
  topology.py      # J1,J2,J3 + link lengths + timings from config.yaml
  ingress.py       # SEC-1,3,4  auth, freshness window, replay/nonce cache
  registry.py      # SEC-2, ARB-7  authorized-vehicle + cert/permission store
  plausibility.py  # SEC-5,6  position/speed/heading sanity vs MAP + prior track
  arbiter.py       # ARB-1..8  priority order, FCFS, queue bound, writer epoch
  leases.py        # FSM-8  lease grant/renew/expire (TTL) → auto-revert
  coordinator.py   # CO-1..7  offsets, ETA arming, hand-off, storage, recovery
  controller.py    # FSM-1..10  per-junction FSM: clearance/min-green/ped/dwell/dilemma
  monitor.py       # MON-1..10  INDEPENDENT latching conflict monitor (separate process/thread)
  audit.py         # SEC-8  hash-chained event log
  engine.py        # 10 Hz tick: telemetry → pipeline steps 1-7 → monitor → broadcast
  app.py           # FastAPI WS/REST gateway (Plan §4)
  config.yaml      # timings (green/amber/all-red/min-green/ped floor), lease TTL, topology
tests/
  test_invariants.py     # the always-true oracle (below) — run against every scenario
  test_controller.py test_arbiter.py test_coordinator.py
  test_security.py       # auth/replay/plausibility/rate-limit
  test_failure_modes.py  # FAIL-1..8: comms loss, telemetry drop, stuck call, split-brain, spoof, flood
```

## Data & time model

- **Junction:** `{ns, ew ∈ {green,amber,red,off}, green_age, mode: normal|preempt|flash|recover, owner_lease, writer_epoch}`.
- **Lease:** `{junction, amb_id, epoch, granted_at, ttl_ms, renew_by}` — the whole fail-safe rests on this expiring.
- **Writer epoch** (FAIL-5): monotonic per junction; the edge/FSM ignores any command whose epoch is below the last accepted → split-brain/stale-command protection.
- **Clocks:** use a monotonic clock for TTLs; enforce the freshness window on wall-clock timestamps with skew tolerance.

## Build order — safety floor first

The earlier plan built features first; for a bulletproof system, **build the safety floor before any priority/coordination feature**, so every later layer can only call *into* a controller that is already safe.

- **Phase 0 — Skeleton:** `contracts.py`, `topology.py`, `engine.py` tick, `app.py` WS broadcast of dummy state. Frontend connects.
- **Phase 1 — One safe junction:** `controller.py` FSM with min-green + full yellow/all-red + ped floor + dwell (FSM-1..7). No preemption yet — just a correct signal.
- **Phase 2 — Independent monitor + invariant tests:** `monitor.py` (MON-1..7) and `test_invariants.py`. **Prove the safety floor holds before adding anything.** This is the gate that makes the rest trustworthy.
- **Phase 3 — Arbiter + leases + fencing:** `arbiter.py`, `leases.py` (ARB-1..8, FSM-8, FAIL-5). Now preemption exists, bounded and time-limited.
- **Phase 4 — Corridor coordinator:** `coordinator.py` (CO-1..7) — the 3-junction green wave, hand-off, recovery, downstream storage.
- **Phase 5 — Security + audit:** `ingress.py`, `registry.py`, `plausibility.py`, `audit.py` (SEC-1..10). Reuse the repo's `auth.py`/`sim_server.py` for HMAC+nonce+freshness.
- **Phase 6 — Failure-mode & fuzz tests:** `test_failure_modes.py` (FAIL-1..8) + a request flood/fuzz soak. This is where "bulletproof" is earned.
- **Phase 7 — Package/deploy:** Dockerfile / compose, `run.md`, point the frontend at the socket.

## The invariant oracle (assert continuously, every test)

Any violation is a bug, no matter the inputs:

1. No conflicting greens / dual indication, ever (MON-1,2).
2. Every green→red passes through full yellow + all-red; never yellow→green (FSM-1,2).
3. Min-green respected before any switch (FSM-4).
4. Pedestrian clearance never below the calculated floor except under true preemption geometry (FSM-5).
5. Every hold is time-bounded and reverts on lease/duration expiry (FSM-8, FAIL-2).
6. Exactly one preempt served per junction; rail>EV>transit honored; higher overrides lower (ARB-1,4).
7. No unauthenticated or implausible request ever produces a grant (SEC-1,5).
8. The monitor latches on fault and can't be cleared by corridor logic (MON-7).
9. On comms/heartbeat loss the system reaches a safe state (local actuated / flash), never a stuck green (FAIL-1,4, SEC-9).

## What to reuse from your repo

- `ambulance-unit/agent/auth.py` — HMAC signing + per-message nonce is your `ingress.py` signing side.
- `ambulance-unit/tools/sim_server.py` — the `verify()` with signature + freshness window + nonce replay-cache + trip idempotency is Phase-5 layer 1, already written.
- `smart_ambulance_sim/` (schemas/junction/corridor/timing/arbitration/control_plane) — the arbiter/timing/lease concepts port straight into `arbiter.py`/`leases.py`/`controller.py`.
- The 43-case test suite pattern → extend into `test_invariants.py` + `test_failure_modes.py`.

## Handoff line for the new chat

"Build a FastAPI + WebSocket green-corridor server per `Backend_Server_Plan_3Junction_Corridor.md` (contract) and `Green_Corridor_Requirements_Catalog.md` (requirements), following the pipeline and safety-first phase order in `Backend_Build_Guide.md`. Start at Phase 1 (one safe junction) and do not proceed past Phase 2 until the invariant tests pass."
