# LifeLine — Program Build Plan

Standalone (no CITS), ambulance-only, simulation-first. Follows the phase order in `docs/Backend_Build_Guide.md`; this file makes it concrete: what gets coded, in what order, and what "done" means per phase.

## Components

| # | Component | Status | Where |
|---|-----------|--------|-------|
| A | **Corridor server** — auth → registry → plausibility → arbiter → lease → coordinator → per-junction FSM → independent monitor; FastAPI + WS, 10 Hz engine | **to build** | `server/` |
| B | **Test harness** — invariant oracle, C1–C12, Chennai matrix, failure/fuzz | **to build** | `tests/` |
| C | **Operator console** — control-room view: junction lamps, leases, monitor faults, command/audit stream, dispatch + scenario buttons, kill-server | **to build (minimal)** | `ops/` |
| D | **Ambulance unit** — driver dashboard + Pi agent | **exists** (`~/Downloads/ser`) | needs 2 small changes (below) |
| E | **Config** — `config.yaml` (generic J1–J3) → `config.chennai.yaml` (EVR pilot, all Mode B) | **to build** | `server/` |

## Is the existing front end enough?

**The vehicle side — yes, nearly.** The `ser` ambulance-unit already covers: SOS + trip setting, GPS (sim + NEO-M8N serial), HMAC-signed events, auto-reconnect, corridor/hazard/reroute display, and the correct security posture (dashboard never holds cloud credentials; vehicle is a client only, controls no signal). Two changes needed:

1. **Transport bridge.** The agent speaks **Socket.IO** (`vehicle:telemetry`, `vehicle:sos`, …) to `:4000`; the server contract is **native WebSocket** envelopes at `/ws`. Decision: the server hosts **both** — native WS for ops/tests (the canonical contract) plus a thin Socket.IO gateway that translates `vehicle:*` events into the same ingress pipeline (the `mock_server.py` pattern proves this works). The `ser` code stays untouched.
2. **Explicit grant semantics (MON-8 / SEC-10).** The CorridorPanel must render the server's explicit `granted / queued / rejected` per junction — the driver must never *assume* right-of-way. Small mapping change in `corridor:update` handling once the server sends real states.

**The system side — no.** `ser` is only the *in-vehicle* half. There is no control-room/junction front end: nothing shows lamp states, leases, monitor faults, or the audit stream, and nothing can dispatch test scenarios. The old repo's HTML simulators are demo-ware, not wired to a live server. So component **C (operator console)** is part of this build — one page rendering the server's broadcast (`junctions / leases / ambulances / commands / server_status`) with Dispatch, Scenario C1–C12, and Kill-server controls. It doubles as the pilot's operator console per `docs/Build_Requirements.md` §1.

## Phase plan (each phase ships runnable + tested)

**P0 — Skeleton & contract.**
Build: `contracts.py` (Pydantic envelope + message types), `topology.py` + `config.yaml` (J1–J3, links, timings), `engine.py` (10 Hz tick loop), `app.py` (FastAPI: native `/ws` broadcast + Socket.IO vehicle gateway), `ops/index` stub page.
Exit: ops page shows dummy junction state ticking; the **unmodified** `ser` agent connects and its telemetry reaches the server log.

**P1 — One safe junction.**
Build: `controller.py` FSM — normal NS/EW cycle, min-green, full amber + all-red, ped-clearance floor, dwell, dilemma-zone hold. No preemption.
Exit: `test_controller.py` proves lamp sequences; ops page shows a correctly cycling junction.

**P2 — Independent monitor + invariant oracle. ← THE GATE**
Build: `monitor.py` as a separate task watching *commanded outputs*: conflicting greens, dual indication, dark head, short clearance, heartbeat timeout → latched flash-red, not clearable by corridor logic. `tests/test_invariants.py`: the 9 invariants asserted continuously + randomized-input fuzz ticks.
Exit: all 9 invariants hold under fuzz. **Nothing further is built until this passes.**

**P3 — Arbiter + leases + fencing.**
Build: `arbiter.py` (Code Red > Code Blue > FCFS > id; one owner/junction; bounded queue; reservice throttle), `leases.py` (TTL grant/renew/expire → auto-revert), writer epoch.
Exit: single-junction preemption works; kill telemetry mid-hold → junction reverts on TTL (C9-type); min-green honored (C11-type); Red overrides Blue (C7-type at one junction).

**P4 — Corridor coordinator.**
Build: `coordinator.py` — offsets (link ÷ progression speed), ETA look-ahead arming, rolling hand-off, downstream-storage check, multi-cycle recovery.
Exit: C1–C4 pass headless; ops page shows the 3-junction green wave rolling.

**P5 — Contention.**
Build: cross-approach conflicts, simultaneous preempts, wave break + resume.
Exit: C5–C8 pass.

**P6 — Security + audit + Chennai config.**
Build: `ingress.py` (port `sim_server.py`'s verify: HMAC + freshness + nonce replay-cache), `registry.py`, `plausibility.py` (on-approach, no teleport, stale-fix rejection, rate limit), `audit.py` (hash-chained), `config.chennai.yaml` (EVR MMC→Vepery→Kilpauk, all `cits_adaptive: false`, peak/off-peak profiles, simulated rail-gate feed).
Exit: CH-R3/R4/R5 analogs pass (spoof, stale GPS, unsigned/replay rejected + audited); rail-gate veto works with `assume_closed` on unknown.

**P7 — Failure modes, fuzz, package.**
Build: `test_failure_modes.py` (FAIL-1..8: comms loss, telemetry drop, stuck call, hung controller, split-brain, spoof, flood) + soak run; then Dockerfile/compose + `run.md`; final end-to-end demo: `ser` dashboard → server → ops console.
Exit: **definition of done — every CRIT row of the Chennai matrix (minus deferred Mode-A rows) passes with invariants asserted continuously, peak + off-peak.**

Deferred to the very end (post-P7, only if/when CITS is real): Mode-A adapter behind an interface + CH-C12 reject handling.

## Order of work in a session

Each phase: write module → write its tests → run headless → show on ops page → commit to this folder. The invariant oracle from P2 runs in every later phase's tests — it is never switched off.
