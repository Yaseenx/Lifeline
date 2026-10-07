# Chennai Backend — Integration Spec & Test Matrix

The Chennai-curated companion to `config.chennai.yaml`. It says how the green-corridor server plugs into Chennai's actual infrastructure, the Chennai-specific hard rules, a phased rollout, and a test matrix that maps the corridor cases and catalog invariants to **real Chennai junctions**. Read it with: the WS contract (`Backend_Server_Plan_3Junction_Corridor.md`), the universal safety rules (`Green_Corridor_Requirements_Catalog.md`), the pipeline/phase order (`Backend_Build_Guide.md`), and the source data (`Chennai_Transport_Study_and_Calibration.md`).

> **[2026-07-03 project decision]** CITS is ON HOLD — build fully standalone (Mode B everywhere, own independent monitor). Mode-A/CITS references below are retained for the end-stage adapter only.

## 1. Integration architecture (Chennai-specific)

```
 108 / EMRI ambulance          ┌──────────────────────────────┐        CITS adaptive controllers
 GPS + auto-dispatch  ──SRM──► │  Green-Corridor Server        │ ──req► (Mode A: request into CITS)
 (telemetry trigger)           │  (auth→plausibility→arbiter→  │        └ or Mode B: drive lamps
                               │   lease→coordinator→FSM→      │           under independent monitor
 Southern Railway ──gate────►  │   safety monitor)             │ ◄stat─  SSM / signal state
 level-crossing status         │                              │
 MTC Chalo GPS ──background──►  └───────────────┬──────────────┘
                                                │ hosted at / coordinated via
                                   GCTP HQ Vepery (TMC)  ·  Smart City ICCC/ITMS (actuation)
                                   governed by CUMTA (statutory sponsor)
```

- **Trigger feed:** the 108/EMRI stack already emits ambulance GPS + ETA + automated dispatch — subscribe to it as the preemption trigger (with plausibility gating; dense-city GPS is noisy).
- **Actuation:** where a junction is CITS-adaptive (`cits_adaptive: true`), issue a **Mode A** priority request into the CITS controller (via the ICCC/ITMS layer) — this automates the *manual ambulance override CITS already ships with*. Where it isn't, fall back to **Mode B**: drive the lamps directly under our independent safety monitor.
- **Host / authority:** the server runs as a corridor service coordinated from **GCTP HQ, Vepery** (the CITS TMC), sponsored/authorised through **CUMTA** (the only body with statutory cross-agency authority). Road-owner fragmentation (GCC / TN Highways / NHAI) is why CUMTA is the sponsor.
- **Hard external input:** the **Southern Railway level-crossing status feed** is a top-priority veto (see §3).

The request-processing pipeline itself is unchanged from `Backend_Build_Guide.md` (auth → registry → plausibility → arbiter → lease → coordinator → per-junction FSM → independent safety monitor). Chennai only sets the *parameters* (`config.chennai.yaml`) and the *integration endpoints* above.

## 2. Mode A vs Mode B (per junction)

Driven by `cits_adaptive` in the config. In the starter config, **8 of 12 junctions are Mode A** (CITS-adaptive: MMC, Vepery, Kilpauk, Koyambedu on EVR; Spencer, Gemini, Guindy, Kathipara on Anna Salai) and **4 are Mode B** (Aminjikarai, Anna Nagar, Nandanam, Saidapet). As CITS commissioning completes (target Aug 2026), flip junctions to Mode A by setting the flag — no code change. → **[superseded 2026-07-03: all junctions start Mode B / `cits_adaptive: false`]**

The one blocking unknown for Mode A is the **controller protocol** (NTCIP 1202 vs proprietary CoSiCoSt/SCATS). Resolve with L&T/CSCL before building the Mode-A adapter; keep the adapter behind an interface so the rest of the server is protocol-agnostic.

## 3. Chennai-specific hard rules

1. **Rail level-crossing gate is un-preemptible and outranks everything** (`priority.order[0]`). If a crossing on the active route is closing/closed, the server must not hold or request greens that discharge toward it; the ambulance holds or reroutes. If crossing status is unknown, `fail_state: assume_closed`. Chennai has grade-separated most core crossings, so this is rare — but it is a hard safety veto and needs the live Southern Railway registry.
2. **Pedestrian clearance floor is preserved** even under preemption at retail/high-footfall junctions (T. Nagar / Panagal Park type). Chennai's pedestrian fatality share is 34% (64% mid-block), so `ped_walk_speed_mps: 1.2` + `ped_buffer_s: 3` is a floor the FSM cannot cut (catalog FSM-5).
3. **Two-wheeler, non-lane-based saturation.** Clearance/queue models use PCU with two-wheeler front-loading, not HCM defaults (study §2). Affects how long a junction needs before it's actually clear.

## 4. Phased rollout (tracks CITS deployment)

- **Pilot — EVR Periyar Salai, 3 live CITS junctions** (MMC/Vepery/Kilpauk): one hospital-bound corridor to Kilpauk MC / RGGGH. Prove Mode A + the full pipeline + invariants on the "med street."
- **Phase 2 — full EVR corridor** (add Aminjikarai, Anna Nagar as they turn adaptive; Mode B until then) to Koyambedu.
- **Phase 3 — Anna Salai** (Omandurar + Apollo access; Gemini/Guindy/Kathipara).
- **Phase 4 — Inner Ring Road (JN Salai)** cross-town, linking to MIOT/Porur and northern hospitals.

## 5. Test matrix (maps cases + catalog invariants to real junctions)

Run headless against the config; assert the referenced invariant (INV-# from `Green_Corridor_Requirements_Catalog.md` §7). C = corridor case, R = Chennai-specific.

| ID | Scenario | Corridor / junction(s) | Setup / trigger | Expected result | Invariant | Crit |
|----|----------|------------------------|-----------------|-----------------|-----------|------|
| CH-C1 | Single-ambulance green wave | EVR: MMC→Koyambedu | one Code Red, offsets = link/4.5 mps (peak) | never stops; each junction greens just before arrival | INV-2,3 | CRIT |
| CH-C2 | Rolling hand-off | EVR full | same, watch releases | each junction reverts as the amb clears it | INV-5 | CRIT |
| CH-C3 | Platoon | EVR | Code Red then Code Blue, same dir | both served; leases renew; order preserved | INV-6 | REC |
| CH-C4 | Opposing corridor | EVR | amb west-bound + amb east-bound | opposing through both served (compatible) | INV-1 | REC |
| CH-C5 | Cross vs corridor | J_KILPAUK | corridor amb + amb on cross street to Kilpauk MC | arbitrated at Kilpauk; MMC/Koyambedu untouched | INV-6 | CRIT |
| CH-C6 | Convergence | J_GEMINI (Anna Salai) | corridor + cross arrive together | sequenced with full yellow+all-red | INV-2,6 | CRIT |
| CH-C7 | Red interrupts Blue wave | J_VEPERY | Code Red crosses a Code Blue wave | Blue holds, Red served, wave resumes | INV-6 | CRIT |
| CH-C8 | Two simultaneous preempts | EVR J_MMC + Anna Salai J_GUINDY | two ambulances, different junctions | independent controllers, both served | INV-1,8 | REC |
| CH-C9 | Comms loss (108 feed drop) | EVR mid-corridor | drop telemetry between Kilpauk & Koyambedu | lease TTL expires → junctions revert; no stuck green | INV-5,9 | CRIT |
| CH-C10 | Monitor trip | J_KOYAMBEDU | force a conflicting-green command | junction latches flash-red; MMC/Vepery/Kilpauk keep running | INV-1,8 | CRIT |
| CH-C11 | Min-green hold | J_GEMINI | cross just turned green when request arrives | honors min_green (7 s) before switching | INV-3 | CRIT |
| CH-C12 | Mode-A reject | J_ANNANAGAR (Mode B) / adaptive junction declines | CITS declines preemption | wave served elsewhere; amb obeys lights here | INV-9 | REC |
| CH-R1 | **Rail-gate override** | any route crossing a live LC | Southern Railway feed: gate closing | preemption yields; amb holds/reroutes; un-preemptible | INV-6,9 | CRIT |
| CH-R2 | **Ped-clearance floor** | retail junction (T. Nagar type) | preempt during pedestrian phase | ped clearance never below crossing_len/1.2 + 3 s | INV-4 | CRIT |
| CH-R3 | **GPS spoof / implausible** | any | inject off-route / teleporting position | plausibility gate rejects; no grant | INV-7 | CRIT |
| CH-R4 | **Stale 108 GPS (urban canyon)** | Anna Salai core | fix older than gps_stale_ms | no preempt on stale fix; wait for fresh | INV-7 | CRIT |
| CH-R5 | **Unsigned / replayed request** | any | send unsigned or replayed SRM | rejected at ingress; audited | INV-7 | CRIT |

Definition of done for the Chennai build: every CRIT row passes with its invariant asserted continuously, on the real-config corridors, at both peak and off-peak speed profiles.

## 6. Open questions to confirm with stakeholders (study §7)

- **CITS controller protocol** (NTCIP 1202 vs proprietary) and **adaptive engine** (SCATS / CoSiCoSt) — L&T / CSCL. Blocks the Mode-A adapter. → **[deferred to end stage]**
- **Citywide signalised-junction count** and per-junction CITS status — GCTP (to flip `cits_adaptive` accurately).
- **Authoritative remaining rail level crossings** in the metro area — Southern Railway (Chennai Division) / GCC Bridges Dept (to populate `level_crossings.known`).
- **Surveyed junction geometry** (crossing widths, approach distances) and **per-corridor speed/queue data** — from CITS sensors or a short field study (replaces the APPROX values).
- **108/EMRI feed access** (API, auth) — TN Health / EMRI Green Health Services.

## Sources

All figures and the integration facts above are cited in `Chennai_Transport_Study_and_Calibration.md`. Load-bearing primary sources: CITS scope/status ([Construction World](https://www.constructionworld.in/policy-updates-and-economic-news/centre-approves-chennai-intelligent-transport-system/93786), [Outlook/PTI](https://www.outlookindia.com/national/centre-approves-rs-530-cr-for-intelligent-transport-system-in-chennai-2)); adaptive signals + ambulance override + Phase-1 corridors ([Telangana Today/IANS](https://telanganatoday.com/chennai-to-roll-out-ai-powered-adaptive-traffic-signals-at-165-junctions)); calibration speeds/LOS ([Frontiers 2025](https://www.frontiersin.org/journals/sustainable-cities/articles/10.3389/frsc.2025.1684489/full), [TomTom](https://www.tomtom.com/traffic-index/city/chennai)); 108 telemetry ([eHealth/Elets](https://ehealth.eletsonline.com/2024/12/emri-green-health-services-pilots-real-time-tracking-and-automated-ambulance-dispatch-in-tamil-nadu/)); rail crossings ([Rail Analysis](https://news.railanalysis.com/southern-railway-completely-eliminates-unmanned-and-manned-level-crossings-in-tamil-nadu/)); governance ([CUMTA](https://www.cumta.tn.gov.in/)).
