# Requirements to Build the Chennai Green-Corridor System

Two layers of "requirements":

- **What it must do** (functional + safety) is already specified — see `Green_Corridor_Requirements_Catalog.md` (~50 cited rules + the invariant oracle), `Backend_Server_Plan_3Junction_Corridor.md` (WS contract), `Backend_Build_Guide.md` (pipeline + phase order), and `Chennai_Backend_Spec_and_Test_Matrix.md` (Chennai specifics). Nothing new is needed there.
- **What you need to build & deploy it** (this doc) — the stack, data, integrations, hardware, security, people, environments, and approvals.

The single biggest determinant of scope is **Mode A vs Mode B**: integrating into the existing CITS controllers (Mode A — mostly software) is far lighter than driving signal lamps yourself (Mode B — regulated field hardware). Aim for Mode A where CITS is adaptive; Mode B only where it isn't.

> **[2026-07-03 project decision — supersedes the line above]** CITS is ON HOLD: deployment status unknown. Build fully standalone (Mode B everywhere, our own independent safety monitor). CITS/Mode A is a thin end-stage adapter behind an interface, considered only at the very end.

## 1. Software & tech stack

- **Runtime / framework:** Python 3.11 + FastAPI + WebSocket + `asyncio` (matches the existing repo). Node/Express is a viable alternative.
- **Core libs:** `pydantic` (message contracts), `pyyaml` (load `config.chennai.yaml`), `uvicorn`; `pytest` for the test suite.
- **State / storage:** in-memory for the pilot; **Redis** (optional) for lease sharing at scale; **Postgres/SQLite** for the hash-chained audit log and config.
- **Crypto:** an HMAC/signing library (you already have `auth.py`); if you go the V2X route later, an IEEE 1609.2 stack.
- **Geo / routing:** OSM network (Geofabrik India extract) + a routing engine (OSRM) for real routes; haversine/geometry helpers.
- **Console / UI:** the interactive sims you already built serve as the operator console for the pilot; a hardened ops dashboard comes later.

## 2. Data & inputs

- **Road network:** routable OSM data for Chennai; CMDA hierarchy for classification.
- **Junction inventory + geometry:** the CITS junction list, and per-junction approaches, crossing widths, and current signal timings — to replace the **APPROX** values in `config.chennai.yaml`.
- **Corridor traffic data:** per-corridor speeds, queues, saturation (from CITS sensors or a short field study) to calibrate offsets and clearance.
- **Hospitals:** verified coordinates/entrances.
- **Rail crossings:** the authoritative list of remaining active level crossings **plus a live gate-status feed** (Southern Railway) — for the un-preemptible veto.
- **Ambulance telemetry:** the 108/EMRI GPS + dispatch feed (the preemption trigger).
- **Authorized-vehicle registry:** which vehicles/classes may request preemption (and their credentials).

## 3. Integrations & access (agreements, not just APIs)

- **CITS / ICCC actuation** — via **L&T** (system integrator) and **CSCL** (authority): the Mode-A request interface and its **controller protocol (NTCIP 1202 vs proprietary)**. *Blocking dependency.* → **[on hold per 2026-07-03 decision; end-stage only]**
- **GCTP (Vepery TMC)** — operational host and the authority that authorizes preemption.
- **CUMTA** — statutory sponsor / MoU giving cross-agency authority (roads are split across GCC / TN Highways / NHAI).
- **TN Health / EMRI** — access to the 108 telemetry + dispatch feed.
- **Southern Railway (Chennai Division)** — level-crossing status interconnect (must be fail-safe).

## 4. Hardware & infrastructure

- **Mode A (light):** servers (at the TMC or cloud) + a comms link into ICCC/CITS. Little to no field hardware — you ride the existing controllers and their conflict monitors. → **[end-stage option only]**
- **Mode B (now the default, regulated):** per-junction **signal controller interface + an INDEPENDENT conflict monitor** (hardware MMU/CMU, NEMA TS2 / EN 12675 class) + a confirmation indication + comms. This is safety-certified field equipment — budget and timeline dominated by it.
- **Comms:** low-latency junction↔TMC link with redundancy; the lease-TTL fail-safe covers dropouts.
- **Server infra:** redundant hosts, monotonic clock source, durable log store.

## 5. Security & trust

- Message **signing + key management** (per-vehicle certificates or a registry), **replay/nonce cache**, and **freshness window** (you already have HMAC+nonce in `auth.py`).
- **Authorized-vehicle registry** + **RBAC** for operators.
- **Hash-chained audit log** store (every request/grant/deny).
- GPS **plausibility gating** service (dense-city GPS is noisy/spoofable).
- If/when V2X: SCMS-style PKI + IEEE 1609.2.

## 6. Team & skills

- Backend / real-time control engineer (state machines, `asyncio`).
- Traffic / ITS engineer (signal timing, NEMA/NTCIP, safety intervals).
- Security engineer (PKI, threat modeling, replay/DoS).
- GIS / routing engineer.
- Integration engineer (works directly with L&T on the CITS interface).
- QA / test engineer (invariant + failure-mode + hardware-in-the-loop).
- Government & clinical liaison (CUMTA / GCTP / EMRI).

## 7. Environments & testing

- **Simulation / software-in-the-loop:** the existing sims + the engine run headless against `config.chennai.yaml`.
- **Hardware-in-the-loop:** a real controller + conflict monitor bench (for Mode B).
- **Closed pilot:** the EVR Periyar Salai 3-junction segment (Vepery/Kilpauk live CITS).
- **Test suite (definition of done):** the 17-row Chennai test matrix + the catalog invariant oracle, run at peak and off-peak; plus failure-mode, fuzz, and soak tests. Every CRIT row must pass.

## 8. Governance, legal & approvals

- **CUMTA MoU** (sponsorship + cross-agency authority) and **GCTP operational sign-off**.
- **TN Health / EMRI data agreement** (108 feed).
- **Southern Railway interconnect** approval (fail-safe, per rail-preemption practice).
- **Authorized-operator legal basis** — who may preempt, with accountability via the audit log.
- **Safety certification** of any Mode-B edge/monitor equipment to controller standards.
- **Data privacy** handling for GPS/telemetry.

## 9. Prerequisites to resolve FIRST (the blockers)

1. CITS **controller protocol** + adaptive engine — L&T / CSCL. *(Gates the Mode-A adapter.)* → **[deferred to end stage]**
2. Rail **crossing registry + live status feed** — Southern Railway. *(Gates the un-preemptible veto.)*
3. **108/EMRI feed access** (API + auth) — TN Health / EMRI. *(Gates the trigger.)*
4. **Surveyed junction geometry + corridor speeds** — replaces the APPROX config. *(Gates accurate offsets/clearance.)*
5. **CUMTA sponsorship / MoU** — the authority to deploy at all.

## 10. Indicative effort

- **Software core** (pipeline: auth → plausibility → arbiter → lease → coordinator → FSM → independent monitor + tests), building on the existing repo, per the Build-Guide phases: a small team over a few months to a validated simulation + pilot-ready server.
- **Mode-A pilot** on 3 EVR junctions: dominated by the L&T/CITS integration lead time, not code. → **[deferred]**
- **Mode-B field deployment**: dominated by certified hardware procurement, installation, and safety sign-off — the long pole.

*Everything above is the build/deploy checklist; the behavioural + safety requirements themselves live in the Requirements Catalog and are unchanged by any of these choices.*
