# Chennai Hospital Capability Study — for LifeLine condition-aware routing

**Date:** 2026-07-03 · **Scope:** Chennai (district lists + the metro majors an ambulance inside Chennai would actually use)
**Purpose:** decide, per clinical condition (cardiac / stroke / trauma / burns / paediatric / obstetric), which hospitals the corridor may route to — "nearest **suitable**, not nearest".

## Method & evidence tiers

Three data layers, cross-matched on 2026-07-03:

1. **Official government datasets** (authoritative for *membership*, not staffing): CMCHIS/MA empanelled-hospitals list ("NK48", updated 2026-06-25, with levels + coordinates), high-end-procedures empanelment list (updated 2026-06-19), and the TAEI (Tamil Nadu Accident & Emergency Care Initiative) centres list — all via tn.data.gov.in downloads.
2. **Curated capability registry** (19 hospitals, `chennai-hospitals.json` / `chennai-routing-config.ts`): per-hospital flags — 24×7 cath lab, stroke tier (NONE/THROMBOLYSIS/THROMBECTOMY), trauma level 0–3, burns, NICU/PICU, obstetric ER, STEMI-hub, TAEI.
3. **Cross-check result:** every registry hospital annotated with `officialEvidence` (see `chennai-hospitals.enriched.json`).

**Read capabilities as evidence-graded:** OFFICIAL (on a government list) > REGISTRY (curated, marked `UNVERIFIED` pending phone confirmation) > CLAIMED (hospital marketing). Empanelment for cardiology is *evidence* of a cath lab, **not proof it is staffed tonight** — final confirmation is an operational phone-verification pass (the `ingest_official_lists.py` philosophy).

## Corrections found by the cross-check

1. **Omandurar (TN Govt Multi Super Speciality)** — registry said `isTaeiCentre: false`; the official TAEI list includes Government Omandurar Medical College → **corrected to true**.
2. **Institute of Child Health, Egmore** — registry said `isTaeiCentre: false`; ICH is on the official TAEI list → **corrected to true**. Chennai's TAEI network therefore includes a *dedicated paediatric* emergency centre.
3. Data quirk to carry: NK48 lists **Kalaignar Centenary Super Speciality Hospital (Guindy)** under directorate "Pvt" — it is a government hospital.

## Capability matrix (19 metro majors, corrected)

| Hospital | Area | Sector | Cath 24×7 | Stroke | Trauma | Burns | NICU/PICU | Ob ER | STEMI hub | TAEI (official) | CMCHIS |
|---|---|---|---|---|---|---|---|---|---|---|---|
| RGGGH / Madras Medical College | Park Town | Govt | ✓ | Lysis | **L1** | ✓ | ✓ | ✓ | **✓** | **✓** | L1 Chennai |
| Govt Stanley MCH | Old Washermanpet | Govt | ✓ | Lysis | **L1** | ✓ | ✓ | ✓ | **✓** | **✓** | L1 Chennai |
| Govt Kilpauk MCH | Kilpauk | Govt | ✓ | Lysis | L2 | **✓** | ✓ | ✓ | **✓** | **✓** | L1 Chennai |
| Govt Royapettah Hospital | Royapettah | Govt | — | Lysis | L2 | — | — | ✓ | — | **✓** | L1 Chennai |
| Kalaignar KCSSH | Guindy | Govt | ✓ | Lysis | L2 | — | — | — | **✓** | — | L1 Chennai |
| TN Govt MSSH Omandurar | Omandurar Estate | Govt | ✓ | Lysis | L2 | — | — | — | — | **✓** (corrected) | L1 Chennai |
| Institute of Child Health | Egmore | Govt | — | — | — | — | **✓** | — | — | **✓** (corrected) | L1 Chennai |
| Inst. of Obstetrics & Gynaecology | Egmore | Govt | — | — | — | — | ✓ | **✓** | — | — | L1 Chennai |
| Apollo Hospitals | Greams Road | Pvt | ✓ | **Thrombectomy** | L1* | — | ✓ | ✓ | — | — | L1 Chennai |
| MIOT International | Manapakkam | Pvt | ✓ | **Thrombectomy** | **L1** | **✓** | ✓ | ✓* | — | — | L1 Kancheepuram |
| Gleneagles Global Health City | Perumbakkam | Pvt | ✓ | **Thrombectomy** | L1 | — | ✓ | ✓ | — | — | (high-end, Kanchipuram) |
| Kauvery Hospital | Alwarpet | Pvt | ✓ | **Thrombectomy** | L2 | — | ✓ | ✓ | — | — | L1 Chennai |
| MGM Healthcare | Aminjikarai | Pvt | ✓ | Lysis | L2 | — | ✓ | ✓ | — | — | L1 Chennai |
| SIMS Hospital | Vadapalani | Pvt | ✓ | Lysis | L2 | — | ✓ | ✓ | — | — | L1 Chennai |
| Sri Ramachandra MC | Porur | Pvt | ✓ | Lysis | L2 | — | ✓ | ✓ | — | — | L2 Kancheepuram |
| Dr. Rela Institute | Chromepet | Pvt | ✓ | Lysis | L2 | — | ✓ | ✓ | — | — | L1 Chengalpattu |
| MGM Malar (ex-Fortis) | Adyar | Pvt | ✓ | Lysis | L2 | — | ✓ | ✓ | — | — | L1 Chennai |
| Madras Medical Mission | Mogappair East | Pvt | ✓ | — | L2 | — | ✓ | ✓ | — | — | L2 Tiruvallur |
| Frontier Lifeline | Mogappair East | Pvt | ✓ | — | L0 | — | — | — | — | — | L2 Tiruvallur |

\* flagged `lowConfidenceCapabilities` in the registry (Apollo traumaLevel, MIOT obstetricEr). All registry rows carry `verificationStatus: UNVERIFIED` until the phone pass.

## Condition coverage — what routing must know

**CARDIAC (needs 24×7 PCI).** Government STEMI hubs: RGGGH, Stanley, Kilpauk, Kalaignar KCSSH. Private PCI-capable: Apollo Greams, MIOT, Kauvery, MGM, SIMS, SRMC, Rela, Malar, MMM, Frontier (cardiac-specialty, but trauma L0 — cardiac-only destination). Coverage is good city-wide; north Chennai relies on Stanley.

**STROKE (lysis floor; LVO needs thrombectomy).** Thrombectomy tier is *entirely private and central/south*: Apollo Greams, MIOT, Gleneagles, Kauvery. Government + rest = thrombolysis only. **Gap: no thrombectomy centre in north Chennai** — an LVO stroke in Royapuram/Tondiarpet means lyse at Stanley and transfer ("drip and ship"), or a longer corridor straight to a thrombectomy centre. This is exactly the decision the routing engine must encode.

**TRAUMA.** Official TAEI centres (6): RGGGH, Stanley, Kilpauk, Omandurar, Royapettah, ICH. L1 heavies: RGGGH, Stanley, MIOT (private benchmark), Apollo*, Gleneagles. Kilpauk runs the "zero-delay ward" concept.

**BURNS — the scarcest capability.** Kilpauk MCH (the classic burns centre), RGGGH, Stanley; **MIOT is the only private burns flag**. Burns routing therefore has just 4 candidates city-wide.

**PAEDIATRIC.** ICH Egmore is the anchor (govt, TAEI, CMCHIS L1). Private PICU: Apollo, MGM, MMM (+ most tier-1s flag NICU/PICU). **Registry gap:** Kanchi Kamakoti CHILDS Trust (Nungambakkam) and Rainbow Children's (Guindy) are not yet entered.

**OBSTETRIC.** IOG Egmore is the anchor. **Registry gaps:** Govt Kasturba Gandhi Hospital (Triplicane — on the high-end list via ENT row, so it exists in official data) and Govt RSRM Lying-in (Royapuram) should be added.

## The official Chennai-district layer (the "all hospitals" baseline)

**CMCHIS-empanelled, Chennai district — 26 institutions** (10 govt / 16 pvt; 16×L1, 7×L2, 3×L3). Beyond the majors above, the list adds: Chennai National Hospital (L1, George Town), Promed Kottivakkam (L1), Apollo Tondiarpet (L2 — **valuable north-Chennai node**), Bharathirajaa T. Nagar (L2), Dr. Mehta's Chetpet (L2), Prashanth Velachery (L2), VHS Taramani (L2), Venkataeswara Nandanam (L2), Pride (L3), Govt Peripheral Hospitals Periyar Nagar & Tondiarpet (L3). Full table: `cmchis-chennai-district-extract.csv`.

**High-end procedure empanelment — 31 Chennai entries** (transplant/BMT/cochlear/bariatric): strong tertiary-depth evidence for RGGGH/MMC, Stanley, Kilpauk, Royapettah, Omandurar CTVS, ICH, KGH, Apollo, Kauvery (+Vadapalani), MGM, SIMS, MIOT, Mehta's, Billroth, Kumaran, Cancer Institute Adyar, KKR ENT, MERF. Full table: `highend-chennai-district-extract.csv`.

**District-boundary caveat (matters for filtering!):** MIOT, SRMC, Gleneagles are empanelled under **Kancheepuram**, Rela under **Chengalpattu**, MMM/Frontier/Mehta-Tiruvallur under **Tiruvallur** — filtering official lists to `district == Chennai` alone would wrongly drop half the metro's tertiary capacity. Clinical routing must use *geography* (travel time), not administrative district.

## Shortlist to add next to the registry

North-Chennai reinforcement first: **Apollo Tondiarpet (L2)**, **Chennai National (L1)**, Peripheral GH Tondiarpet/Periyar Nagar; then specialty anchors **KGH + RSRM (obstetric)**, **CTC CHILDS Trust + Rainbow (paediatric)**; then mid-tier fill-ins: Mehta's, VHS Taramani, Venkataeswara, Prashanth, Bharathirajaa, Vijaya Vadapalani (in no official list found — verify), Billroth, Kumaran, St. Isabel's.

## Operational next steps

1. **Phone-verification pass** on all 19 (script leaves `operationallyConfirmed` open): confirm 24×7 cath-lab staffing, thrombectomy on-call roster, burns beds, ObER theatre. Priority: the 4 thrombectomy claims + 4 burns flags.
2. Ingest the PMJAY hospital PDF (captcha-gated, manual download) via `ingest_official_lists.py` for a second empanelment signal.
3. Add the shortlist hospitals; re-run the enrichment.
4. Serve the enriched registry from the corridor server (P0+) — the dashboard's verified tier then comes from one source of truth.

## Deliverables & sources

`chennai-hospitals.enriched.json` (registry + officialEvidence + 2 corrections) · `cmchis-chennai-district-extract.csv` · `highend-chennai-district-extract.csv` · originals: `chennai-hospitals.{csv,json}`, `chennai-routing-config.ts`, `ingest_official_lists.py`, raw lists from tn.data.gov.in (GODL-India licence: NK48 CMCHIS empanelment 2026-06-25; high-end procedures 2026-06-19; TAEI centres). Registry capability tiers additionally reflect hospital-published programmes (e.g., MIOT Heart Revive / Stroke Restore, Apollo stroke network) — treated as CLAIMED until phone-verified.
