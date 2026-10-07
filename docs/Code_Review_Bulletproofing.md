# LifeLine — Code Review & Bulletproofing Plan

Reviewed 2026-07-04. Scope: `server/` (engine, controller, arbiter, monitor, security, app), `ambulance-unit/agent/`, dashboard, `tests/`. Findings below are ranked by severity; each one I could reproduce is marked **[verified]** with the evidence.

---

## Verdict

The safety *core* is real and well built. The single-junction FSM cannot express an unsafe transition, the independent latching monitor watches only commanded lamps, leases are TTL-bounded, and grants flow through a monotonic "each layer only reduces authority" pipeline. I ran your P2 gate fuzz myself — **120,000 ticks / 200 sim-minutes, zero invariant violations, monitor never tripped.** That claim holds up.

What is *not* yet bulletproof is everything around that core: the multi-vehicle priority handoff, the control plane (ops channel), input trust (GPS/SOS), and the fact that in a real deployment your software is currently the *only* thing preventing a stuck green. Five of these are concrete bugs or holes, not future features.

---

## Critical

### C1. The ops control channel is completely unauthenticated — including the monitor reset **[verified: read `app.py`]**
`@api.websocket("/ws")` accepts any connection with no auth and processes `kill_server`, `restore`, `monitor_reset`, and `force_fault`. Anyone who can reach port 4000 can:
- kill the corridor (`kill_server` → stops all renewals), or
- **clear a latched safety fault** (`monitor_reset`).

Your entire monitor design rests on "only an operator can reset a latched junction" (`monitor.py` docstring, `external_reset`). That guarantee is void: the reset is exposed to any unauthenticated network peer. `cors_allowed_origins="*"` compounds it.
**Fix:** put the ops channel behind authentication (operator login + session token, mutual-TLS, or at minimum a signed control token), lock CORS to the console origin, bind `/ws` to a management interface, and require a second factor / two-person action specifically for `monitor_reset`. Treat ops commands as a privileged control plane, not a debug socket.

### C2. RED-over-BLUE override is delayed by the full lease TTL — priority is not actually promptly enforced **[verified: reproduced, ~2.4 s gap]**
When a `code_red` overrides an active `code_blue`, `arbiter.request()` demotes BLUE and makes RED the owner — but **nothing tells the FSM.** The engine then calls `fsm.request_preempt(RED,…)`, which returns `"rejected"` because `self.lease.owner` is still BLUE (`controller.py:57`). RED cannot take the junction until BLUE's lease **expires on its own** (`lease_ttl_ms = 1500`). In my reproduction the arbiter handed RED ownership at t=5.1 s but RED did not actually hold the green until t=7.5 s — a **2.4 s gap**, during which the FSM kept serving the *demoted lower-priority* vehicle for 16 ticks.

Your test `test_red_overrides_blue_then_blue_regranted` only asserts **arbiter** state, so it passes while this gap is invisible.
**Fix:** on override, the engine (in `_handoff` or a new `_override` path) must explicitly `fsm.release(demoted)` and immediately `fsm.request_preempt(new_owner, …)`. The FSM still clears the demoted movement safely through amber + all-red — but it should *start* clearing the instant priority changes, not 1.5 s later. Add a test asserting the FSM lease owner and lamp state, not just arbiter state.

### C3. Software is the only thing preventing a stuck green; the watchdog can't catch a fully-hung engine **[verified: read `engine.py` + `app.py`]**
`monitor.observe()` is called *from inside* `engine.tick()`. If the engine loop hangs or dies, `tick()` stops running — so `observe()` is never called, the heartbeat watchdog (`monitor.py:44`) never evaluates, and `fsm.tick()` never processes lease TTL. The commanded lamps simply **freeze** at their last value. In simulation that's invisible; on real hardware in Mode B (you drive the signals directly, per README rule 2) a frozen command is a stuck green with nothing to revert it.
**Fix:** the last-resort revert must live *below* your software — the field signal controller / cabinet needs its own dead-man timer (conflict monitor unit) that flashes-red on loss of valid commands. Architecturally: run the monitor as a **separate process** with an independent clock, and drive real junctions through a controller interface (target NTCIP 1211 for signal priority, or the API of Chennai's ATCS) whose hardware MMU is the true safety floor. Never let one Python loop be the only barrier.

---

## High

### H1. No GPS plausibility gating — a valid device can farm greens **[verified: read `engine.telemetry`]**
`telemetry()` trusts `lat`/`lng`/`speed_kph` verbatim. A correctly-signed agent (or a spoofed one, see H2) can teleport, report impossible speed, or fake an approach vector to hold corridors it isn't entitled to. Signatures prove *who sent it*, not *that it's true*.
**Fix:** reject fixes that imply impossible speed/acceleration vs. the previous fix, snap to the road network and reject off-corridor tracks, require a minimum fix quality, and only count "approaching" when heading + position agree. This is your P-list "GPS plausibility gating" — it belongs before P4, not after.

### H2. Authentication is shared-secret HMAC with secrets in plaintext config **[verified: `security.py`, `config.yaml`]**
`config.yaml` ships `AMB-DEV-001: change-me-dev-secret`. The server stores every device's secret in plaintext and can forge any device; anyone who reads the config impersonates the fleet. You've flagged this as dev-grade in the docstrings — good — but it's on the critical path to "bulletproof."
**Fix:** move to per-device **asymmetric** keys (device signs with private key, server verifies with public) as your own `auth.py` comment plans; store private keys in a TPM/secure element on the agent box, never a file; add key provisioning, rotation, and instant revocation (stolen vehicle). Run mTLS under the message signing. Your signing interface already abstracts this, so the blast radius is small.

### H3. SOS is self-asserted, not bound to a dispatched incident **[verified: `main.py` / `engine.sos`]**
Any unit can raise `vehicle:sos` and request preemption. The agent-side hard rule (non-emergency never emits SOS) is enforced well in two places — credit — but nothing ties an emergency to an *authorized* dispatch. A compromised or rogue unit gets green waves on demand.
**Fix:** bind every SOS to a dispatch-issued incident ID that the server validates against your CAD/dispatch record; log grant/deny with that ID in an append-only (hash-chained) audit trail.

### H4. Code Blue can be starved indefinitely **[verified: reproduced — BLUE never promoted after 200 RED cycles]**
The arbiter sort key is `(-class_rank, sos_ts, id)`, so *every* RED outranks *every* BLUE regardless of wait time and there is no aging. With a steady stream of REDs keeping the queue non-empty, a queued BLUE is **never** promoted. Rare on a 3-junction pilot; real on a busy corridor.
**Fix:** add bounded aging or a starvation cap (e.g. after N seconds queued, a BLUE gets a guaranteed service window), and surface queue wait time to ops. Decide the policy deliberately — "RED always wins" may be acceptable, but it should be a *choice*, not an accident of the sort key.

---

## Medium

### M1. Single corridor server is a SPOF. Safe-fails (everything reverts) but mission-fails — one crash and the whole corridor loses preemption. Your epoch fencing already anticipates a takeover; add an active/passive pair with leader election and epoch-fenced handover.

### M2. No persistence or audit trail. `engine.log` is an in-memory ring buffer capped at 200 entries (`_log`). For an emergency-signal system you need durable, tamper-evident logs (who got what green, when, why) for incident review and liability. This is your hash-chained-audit P-item — pull it earlier.

### M3. Replay window is loose. `freshness_window_s = 5.0` accepts messages up to 5 s old; the replay cache only catches byte-identical repeats. Tighten the window, and prune the replay cache by time on every call rather than only when it exceeds 4096 entries (`security.py:47`).

### M4. Google Maps key. It's correctly `.gitignored`, so not leaked to the repo — good. But a Maps JS key is always visible in browser traffic, so it must be locked with HTTP-referrer + API restrictions in the Google console, or it will be scraped and abused.

---

## What's genuinely solid (keep these)

The structural safety guarantees in `controller.py` (min-green guard and amber→green forbidden both `raise`, so an unsafe transition is a crash, not a silent bug); the independent monitor watching commanded lamps with an operator-only latch; lease TTL as the comms-loss fail-safe; monotonically increasing writer epochs for split-brain fencing; the motion hysteresis in `_motion_update` that prevents grant thrash when GPS is slower than the tick; the defense-in-depth hard rule (agent refuses corridors for non-emergency trips *and* `_send_sos_state` gates on emergency); and `connect_forever` minting a fresh signed handshake per attempt instead of replaying a stale one. The P2 gate is a legitimate proof of the single-junction core and I confirmed it passes.

---

## Priority order to "bulletproof"

1. **C1** — lock down the ops control plane (fastest high-impact fix; it currently voids your own safety-reset guarantee).
2. **C3** — put the real fail-safe in the field controller / independent monitor process; write the "engine stalls with a vehicle inside the junction" test.
3. **C2** — wire arbiter override → FSM handoff; test at lamp level, not arbiter level.
4. **H1 + H2 + H3** — trust the *claim*, not just the sender: GPS gating, asymmetric keys, incident-bound SOS.
5. **H4, M1, M2** — aging/anti-starvation, HA pair, durable hash-chained audit.
6. Then formal methods: model FSM + lease + arbiter in **TLA+** and machine-check three properties — no conflicting greens ever, revert within T under arbitrary message loss, no BLUE starvation. Follow with chaos tests (kill/partition mid-crossing), hardware-in-the-loop against a real controller, and an N-ambulance × M-junction load matrix.
7. Before any live signal: a written safety case (HAZOP/FMEA per junction) and GCTP / traffic-police sign-off.

## Chennai reality check

A green is worthless behind a 40-vehicle queue. Preemption must arm **early** from ETA + a queue-length estimate — that's your P4 coordinator and it's the highest-value *feature* gap once the safety items above are closed. Model monsoon flooding (Velachery, Pallikaranai) as dynamic routing constraints, and rely on GPS pin + landmark rather than street address, which is unreliable locally.
