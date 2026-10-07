# LifeLine — Ambulance Green-Corridor System

Project home. Everything built from 2026-07-03 onward lives here.

## Ground rules (locked)

1. **Ambulance only.** Code Red > Code Blue. Other emergency-vehicle classes come after government approval — the arbiter reserves their priority slots but we don't build them.
2. **No CITS dependency.** CITS status is unknown, so the system is fully standalone: we drive the signals ourselves (Mode B) under our own independent safety monitor, everywhere. A CITS/Mode-A adapter is considered only at the very end, behind an interface.
3. **Safety floor first.** Build order is non-negotiable: one correctly-timed junction → independent monitor + invariant tests (the gate) → only then preemption, green wave, security.
4. **Simulation first.** Hardware (A7670 etc.) enters the loop only after the invariants pass in simulation.

## Layout

```
docs/            source-of-truth specs (six research docs)
ambulance-unit/  vehicle front end — Python agent + React dashboard  [built, moved here 2026-07-03]
server/          corridor backend — FastAPI + WebSocket + 10 Hz engine   [to build]
tests/           invariant oracle, C1–C12, Chennai matrix, failure modes [to build]
```

`Ambulance_Project_Memory.md` — consolidated project memory; read this first in any new session.
`BUILD_PLAN.md` — the concrete program build plan (phases, components, front-end gap analysis).

Related code elsewhere:
- `~/Downloads/ser` — original copy of the ambulance unit (superseded by `ambulance-unit/` here)
- `~/Desktop/ambulance project/` — old repo, reference only (Onish-saver-main, smart_ambulance_sim, simulators)

## Build phases

P0 skeleton (WS + topology, front end connects) → P1 one safe junction FSM → **P2 monitor + 9-invariant oracle — GATE** → P3 arbiter + leases + epoch fencing → P4 green-wave coordinator → P5 security + audit → P6 failure/fuzz tests → P7 package. Definition of done: every CRIT row of the 17-row Chennai test matrix passes with invariants asserted continuously, peak + off-peak.
