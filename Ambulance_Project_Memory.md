# Ambulance / Green Corridor Project — Consolidated Memory

**Owner:** Onish (Ashwin@flosil.com, Flosil)
**Last updated:** 2026-07-03
**Product name:** *Flosil LifeLine* (placeholder, not final)
**Code repo:** `~/Desktop/ambulance project/Onish-saver-main`
**Front-end build:** `~/Desktop/LifeLine-Ambulance/ambulance-unit` (moved from `~/Downloads/ser` 2026-07-03; grant-semantics UI added; original in Downloads is superseded)
**Bug-review pass (2026-07-03):** fixed — picker not reflecting actual destination; default destination was always Apollo (now nearest verified-ED from current position); agent default condition 'trauma' unknown to dashboard → now code_red (safe assumption); leg-1 house call without coords no longer draws misleading hospital route. Hospital sources chained Google Places → OSM → CMCHIS fallback with per-mirror timeouts; ETA uses 11 km/h floor when stationary. All re-verified: tsc clean + extended agent behavioral suite.
**ED-aware nearest (2026-07-03):** emergency trips are suggested the nearest hospital with a KNOWN emergency dept (verified tier or OSM emergency=yes; 'unknown' treated as no — conservative), with an explicit "Skipped X — no known emergency dept" note; non-emergency = nearest overall. Dashboard verified tier now = full 19-hospital registry with place-ID coords (fixed wrong map pins).
**Trip model (2026-07-03):** front end implements trip_type (SCENE/HOUSE_CALL/TRANSFER) × emergency × leg. Hard rule enforced agent-side: non-emergency never emits sos and refuses pushed corridors. House call = 2 legs with Patient-onboard flip; escalate/de-escalate live. Verified: tsc clean + agent behavioral test (hard rule, legs, corridor refusal).
**Hospital capability study (2026-07-03):** `docs/Chennai_Hospital_Capability_Study.md` — 19-hospital capability matrix (cath/stroke/trauma/burns/PICU/ObER) cross-checked against official TN datasets (CMCHIS NK48, high-end procedures, TAEI). 2 corrections (Omandurar + ICH are TAEI centres). Key routing facts: thrombectomy = 4 private central/south only (Apollo Greams, MIOT, Gleneagles, Kauvery) — north Chennai gap; burns = 4 only (Kilpauk, RGGGH, Stanley, MIOT); govt STEMI hubs = RGGGH, Stanley, Kilpauk, Kalaignar KCSSH; paeds anchor = ICH Egmore; obstetric = IOG. All flags UNVERIFIED until phone pass. Enriched dataset: chennai-hospitals.enriched.json. Routing config uploaded by Onish: chennai-routing-config.ts (Priority≠Condition, CapabilityRequirement matching).
**Hospitals (2026-07-03):** dashboard live-fetches every mapped hospital within 8 km of the GPS via Overpass/OSM (`hospitalsLive.ts`, `useNearbyHospitals`), merged with a curated verified tier (4 hospitals), nearest-first, `emergency=no` filtered out; verified/empanelled registry (108/EMRI, TN Health) still to come server-side
**Project home (decided 2026-07-03):** `~/Desktop/LifeLine-Ambulance` — everything we build from now on is saved here (specs in `docs/`, server code, tests). Old repo `~/Desktop/ambulance project/` stays as reference (Onish-saver-main, smart_ambulance_sim).

## Current scope (decided 2026-07-03)

**Ambulance only for now.** After getting approval for the ambulance system, extend it to all emergency vehicles (fire, police, etc.). The arbiter's full priority order (rail > fire/EMS > police > transit) is designed in but only the ambulance class is being built/pitched first.

**CITS on hold — build standalone (decided 2026-07-03).** CITS deployment status is unknown (may not even have started), so do NOT depend on it. Build the entire system as if there is no CITS: Mode B (we drive the signals under our own independent safety monitor) is the default everywhere. CITS/Mode A becomes a thin adapter behind an interface, considered only at the very end. Consequences: our safety monitor carries full responsibility (no CITS conflict monitor to lean on); all junctions start `cits_adaptive: false`; the Mode-A adapter and CH-C12-style reject handling move to the final phase.

## What the project is

An ambulance traffic-signal preemption ("green corridor") system for Chennai, pitched to Greater Chennai Traffic Police (GCTP) and Chennai Smart City Ltd (CSCL). Core positioning: **complement CITS, don't compete** —

- **Mode A:** integrate with Chennai's ₹530 cr CITS rollout (AI adaptive signals at 165 junctions)
- **Mode B:** serve the ~147 timer-only junctions CITS won't reach
- Automate the manual green-corridor override the traffic control room already runs (current manual benchmark: 12 km in 14 min)

*(Positioning above is for the government pitch; engineering-wise CITS is on hold per Current scope.)*

## Key numbers (business case)

| Metric | Value |
|---|---|
| Capex (3 years) | ~₹12.3 cr |
| Opex | ~₹2 cr/yr (₹3.5 cr annualised total) |
| Lives saved (modelled, conservative) | 150–450/yr |
| Cost per life | ₹0.8–2.3 lakh |
| Benefit-cost ratio | ~43× |
| Chennai avg speed | 14.6 km/h (TomTom) |
| TN road deaths 2024 | 18,074 |
| 108 EMS avg response | 7.54 min |
| Golden-hour access (India) | only ~20% of victims |

Trip-volume and value-of-life inputs are estimates — swap in Flosil's real figures when available; Excel model flows them through automatically.

## Deliverables produced (by session)

1. **"Smart ambulance idea"** — 15-page pilot proposal for GCTP/CSCL (Word + PDF): exec summary, architecture, CITS integration, safety case, security, test plan (73-case suite), EVR Salai pilot with KPI table, costs, risks, 9-month timeline, governance, 4 appendices (BOM, test cases, priority logic, sources). Flosil + Onish's email on cover.
2. **"Chennai ambulance traffic study"** — 12-page Word study, 12-slide deck (ask: fund a 6-month pilot), 10-tab Excel cost-benefit model (blue/yellow = editable inputs, zero formula errors).
3. **"Chennai emergency response traffic study"** — `Green_Corridor_Requirements_Catalog.md` (~50 cited requirements from NTCIP 1211/1202, MUTCD, FHWA, ARC-IT) + `Backend_Build_Guide.md` + earlier `Backend_Server_Plan_3Junction_Corridor.md`. These three files = single source of truth for the build.
4. **"Green Corridor junction simulator"** — interactive HTML simulator; every test case plays as a full emergency story (accident/house-call origin → pickup → corridor clearance → arrival at Apollo Hospitals). Includes "The Night Shift" demo. Merged with Onish's own parallel edits (`startCaseStory`, hooks, secondary units).
5. **"Ambulance traffic test cases"** — 73-case test suite + hardware tracker Excel (9 components; amber=ordered, green=bought, blue=personal; includes A7670 GSM/LTE module, SIM, multimeter — all bought).

## Architecture — 8-layer defense-in-depth pipeline

Every request is guilty until proven safe; each layer can only *reduce* what gets granted:

1. **Auth** — signature + cert + freshness + replay cache (already written: `auth.py` / `sim_server.py`)
2. **Registry** — vehicle authorization; class comes from registry, never the message
3. **Plausibility** — position on real approach, sane speed/heading, no GPS teleport (GPS spoofable for <$100)
4. **Arbiter** — fixed order: rail > fire/EMS > police > transit; FCFS within class; one owner per junction; bounded queue; writer epoch
5. **Lease** — short TTL, expiry auto-reverts (= the comms-loss fail-safe)
6. **Coordinator** — green-wave offsets (distance ÷ speed), arm next junction by ETA, don't discharge into a full box
7. **Per-junction FSM** — only thing that moves lamps; mandatory min-green + full yellow/all-red, never shortened, never yellow→green
8. **Independent safety monitor** — separate process, latches flash-red on conflicting greens / dual indication / dark head / short clearance / watchdog / low voltage; corridor logic **cannot** clear it

## Non-negotiable rules (from standards research)

- It's **preemption, not priority** — drops coordination, needs managed multi-cycle recovery (30 s–7 min field-measured)
- Clearance intervals inviolable (MUTCD §4D.27)
- Edge keeps final authority: server *requests*, junction *disposes*
- Fail-safe beats obedience: any doubt → safe local state; everything time-bounded, no open-ended greens
- Security is required, not optional: preemption spoofing documented 2003 (Detroit) → 2023 (Flipper Zero); sign every request (IEEE 1609.2/SCMS-style), replay protection, plausibility gating, rate-limiting (SEC-1…10)

**Build order:** safety floor first — Phase 1 = one correctly-timed junction, Phase 2 = independent monitor + invariant tests — only then preemption, green wave, security layers.

## Verified simulator test cases

C1 full phase chain (5 junctions green at entry) · C3 partner unit joins mid-run · C7 J5 flips EW→NS→EW · C9 uplink drop, finishes on normal signals · C11 holds 4.0 s min-green at J7 · C12 J6 never preempts (Mode A) · Night Shift demo · manual emergency button.

## Open items

- Extend to all emergency vehicle classes after ambulance approval
- Merge CRITICAL catalog requirements into `Backend_Server_Plan_3Junction_Corridor.md` as a safety & security section (offered, not confirmed)
- Finalize product name (LifeLine is placeholder) and branding
- Replace estimated trip-volume / value-of-life inputs with Flosil's real figures
- Fix EVR Salai pilot junction-by-junction list via joint survey with GCTP
- Possible short pitch deck / one-page exec brief for first meeting

**Destination + green-countdown chain (2026-07-04):** dashboard sends destination coords in set_trip → agent forwards in vehicle:trip → engine stores dest (id/name/lat/lng, trip_type, leg) → ops map draws destination H marker + dashed heading line + "→ hospital" per ambulance; engine computes eta_green_s from live FSM phase → corridor nodes carry green_in_s (dashboard shows "🟢 in Xs" per signal; ops junction cards too) → agent-mode dashboard now gets real dest_distance_m/dest_eta_sec from server (ETA no longer blank). Agent reconnect fixed (fresh handshake per attempt, library auto-reconnect off); agent sim GPS follows EVR J1→J2→J3 (verified 0 m). All verified: engine tests 10/10, agent behavioral chain, tsc clean.

**Monitoring console (2026-07-03):** ops.html upgraded to full control-room view — Leaflet dark map (no key), junction lamp markers (ring when owned, flash on fault), ambulance markers + path trails + engagement lines (granted/requested/queued/rejected), contention alerts, junction/ambulance panels, live activity log; snapshot enriched with coords/speed/engage per ambulance. WS-validated live.

## Server status (built 2026-07-03) — P0–P3 COMPLETE, P2 GATE PASSED

`server/` + `tests/` in project folder. 10 Hz engine; junction FSM (inviolable clearance, min-green, bounded holds, amber→green impossible by construction); independent latching monitor (flash-red, operator-only reset, watchdog); arbiter (RED>BLUE, FCFS, bounded queue, epoch fencing); lease TTL auto-revert; HMAC+freshness+replay ingress; Socket.IO gateway speaking the agent's protocol (unchanged `ser` agent connects); native WS ops console at :4000 with demo dispatch/kill-switch/fault drill. **12 tests pass** incl. 200-sim-minute invariant fuzz (P2 gate), C7 red-over-blue, C9 comms-loss TTL revert, C10 fault scoping, epoch fencing, demo e2e (granted+passed J1→J3, all revert). Live-verified: authentic agent granted at J1, forged secret refused. Two engine bugs found+fixed during build: grant thrash between GPS fixes (fix: judge approach/recede on fixes with cumulative 1 m hysteresis), demo pass-detection swallowed by hysteresis (fix: cumulative reference). Next: P4 green-wave coordinator, P5 contention, P6 plausibility+audit+Chennai matrix, P7 failure fuzz+packaging. Run: `uvicorn app:app --port 4000` (see server/run.md).

## Build spec (from the six uploaded source docs, 2026-07-03)

- **Stack:** Python 3.11 + FastAPI + WebSocket + asyncio, 10 Hz authoritative tick engine; in-memory state, SQLite/Postgres audit, Redis optional
- **WS contract:** envelope `{payload, ts, nonce, sig}` HMAC-signed; client→server: hello/dispatch/telemetry/scenario/kill_server; server→client: topology/junctions/leases/ambulances/commands/server_status; server-authoritative mode recommended
- **Modules:** contracts, topology, ingress, registry, plausibility, arbiter, leases, coordinator, controller, monitor, audit, engine, app + config.yaml
- **Phases:** P0 skeleton → P1 one safe junction FSM → P2 independent monitor + invariant oracle (**GATE: do not pass until 9 invariants hold**) → P3 arbiter+leases+epoch fencing → P4 green-wave coordinator (C1–C4) → P5 security+audit → P6 failure/fuzz (FAIL-1..8) → P7 package/deploy
- **Cases:** corridor C1–C12; Chennai matrix CH-C1..C12 + CH-R1..R5 (17 rows). **Definition of done: every CRIT row passes with invariants asserted continuously, peak + off-peak**
- **Chennai priority order:** rail gate closed (un-preemptible) > Code Red > Code Blue > normal CITS; ped floor 1.2 m/s + 3 s buffer; PCU two-wheeler saturation model
- **Pilot:** EVR Periyar Salai, 3 junctions (MMC → Vepery → Kilpauk) to Kilpauk MC / RGGGH; then full EVR → Anna Salai → Inner Ring Rd. ~~Starter config 8/12 Mode A~~ → superseded: **all junctions Mode B / standalone; CITS deferred to end**
- **Calibration:** peak 4.5 m/s (floor 4), off-peak 7 m/s progression; ambulance peak crawl ~3 m/s; benchmark ~70% time cut (2014 corridor), 108 baseline 7.54 min
- **Deployment blockers (not code):** ~~CITS controller protocol (L&T/CSCL)~~ (deferred), rail gate feed (Southern Railway), 108/EMRI API, surveyed geometry, CUMTA MoU

## Key sources

TomTom Chennai index · EMRI 108 tracking pilot (eHealth Dec 2024) · Chennai 165-junction CITS · FHWA Signal Timing Manual Ch. 9 · MUTCD §4D.27 · NTCIP 1211 · EDI MMU2-16LE manual · ARC-IT emergency-preempt security triple · US DOT V2I preemption evaluation · Schneier on preemption spoofing · Princeton CITP (default-to-safe)
