# Chennai Transport, Roads & Emergency-Vehicle Study — with Green-Corridor Calibration

An area-specific study of Chennai's roads, traffic, signal/ITS infrastructure, emergency-vehicle ecosystem, and transport governance — and how each finding calibrates the green-corridor backend. Research date July 2026; figures are dated inline and approximations flagged.

**Bottom line up front:** Chennai is unusually favourable ground for this project. It already runs *manual* ambulance/organ green corridors (a decade-old, celebrated practice), it is *mid-deployment* of a ₹530-crore adaptive-signal system (CITS) whose design **already includes a manual "green corridor" override for ambulances**, and the 108 ambulance service already has GPS/auto-dispatch telemetry. The opportunity is to **automate an already-proven manual workflow** by integrating at CITS. Local study doesn't change the safety architecture — it fixes the parameters (speeds, offsets, priority corridors), the integration path (Mode A into CITS), and the one hard local override (rail level-crossing gates).

> **[2026-07-03 project decision]** CITS is ON HOLD (deployment status unknown). The system is built standalone (Mode B everywhere); CITS integration is an end-stage adapter only. Calibration numbers below remain valid.

---

## 1. Road network & geography

Greater Chennai Corporation covers **426 sq km, 15 zones, 200 wards**, and stretches ~43 km along the coast ([GCC Roads Dept](https://chennaicorporation.gov.in/gcc/department/road/)). GCC maintains **471 Bus Route Roads (387 km)** plus **34,640 interior roads (5,270 km)** ≈ **5,657 km** of city road; the wider metropolitan network is ~**2,780 km** (reconcile scopes carefully) ([GCC Roads](https://chennaicorporation.gov.in/gcc/department/road/); [Flyovers in Chennai](https://en.wikipedia.org/wiki/Flyovers_in_Chennai)).

**Primary arterials (candidate corridors):**

| Road | Role | Note |
|---|---|---|
| Anna Salai (Mount Rd) | ~11 km central N–S spine, Fort → Kathipara | CITS Phase-1; historically lane-disciplined ([src](https://en.wikipedia.org/wiki/Anna_Salai)) |
| EVR Periyar Salai (Poonamallee High Rd) | 14 km E–W, Central → Maduravoyal | Chennai's "med street" — highest hospital density; **6 CITS pilot junctions live** ([src](https://en.wikipedia.org/wiki/EVR_Periyar_Salai)) |
| Rajiv Gandhi Salai (OMR) | 45 km IT corridor, 6-lane divided | dense signals; hospitals toward Perungudi ([src](https://en.wikipedia.org/wiki/Rajiv_Gandhi_Salai)) |
| GST Road (NH-32) | Southern airport/inter-city, 4→8 lane | tolled NH, elevated sections ([src](https://en.wikipedia.org/wiki/Grand_Southern_Trunk_Road)) |
| Inner Ring Road (JN Salai) | 25.2 km, 6-lane circumferential | CITS Phase-1; good cross-town routing ([src](https://en.wikipedia.org/wiki/Inner_Ring_Road,_Chennai)) |
| Outer Ring Road | 62 km access-controlled | few at-grade signals; long transfers ([CMDA](https://cmdachennai.gov.in/outerringroad.html)) |
| Sardar Patel Rd, Kamarajar Salai, Rajaji Salai, Taylors Rd | central/coastal arterials | all CITS Phase-1 |

**Major bottleneck junctions to model:** **Kathipara** (Anna Salai + GST + IRR + Mount-Poonamallee cloverleaf; >200,000 veh/day, peak ~10,230 veh/h) ([src](https://en.wikipedia.org/wiki/Kathipara_Junction)); **T. Nagar / Panagal Park** (LOS E–F); **Koyambedu / Maduravoyal** (container + mofussil-bus pileups); **Gemini/Teynampet** (Anna Flyover); **Basin Bridge** (north) ([Frontiers 2025](https://www.frontiersin.org/journals/sustainable-cities/articles/10.3389/frsc.2025.1684489/full)).

**Routing barriers (mandatory pass-points):** the **Cooum River** (central) and **Adyar River** (south) plus the **Buckingham Canal** are continuous barriers crossable only at bridges — a finite set of choke-crossings the router must enumerate (e.g., Sardar Patel Rd over the Adyar) ([Geography of Chennai](https://en.wikipedia.org/wiki/Geography_of_Chennai)). **42+ flyovers/grade separators** offer signal-free segments to prefer ([Flyovers](https://en.wikipedia.org/wiki/Flyovers_in_Chennai)). **Map data:** OpenStreetMap via [Geofabrik India extracts](https://download.geofabrik.de/asia/india.html) is the practical routable source; CMDA Master Plan maps give the official hierarchy ([OpenCity](https://data.opencity.in/dataset/chennai-master-plan-2026)).

## 2. Traffic characteristics & congestion (the calibration numbers)

- **Fleet & mix:** ~**4.9 million** registered vehicles (2023), growing ~10%/yr; **~75–79% two-wheelers** (structural) ([Frontiers 2025](https://www.frontiersin.org/journals/sustainable-cities/articles/10.3389/frsc.2025.1684489/full); [Transport in Chennai](https://en.wikipedia.org/wiki/Transport_in_Chennai)). Flow is **non-lane-based mixed traffic** — two-wheelers filter to the stop-line front, so use **PCU-based saturation flow** and empirically-calibrated start-up loss, not HCM defaults ([PLOS One 2024](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0306112)).
- **Congestion (TomTom 2025):** average **31 min 15 s per 10 km**, **58.6%** congestion; **AM rush ~17.7 km/h**, **PM rush ~14.6 km/h** (evening congestion 100.9%) ([TomTom Chennai](https://www.tomtom.com/traffic-index/city/chennai)).
- **Peak windows:** **AM 08:00–10:30**, **PM 17:00–20:00** (worst ~18:00); rush is 1.5–2× off-peak ([Frontiers 2025](https://www.frontiersin.org/journals/sustainable-cities/articles/10.3389/frsc.2025.1684489/full)).
- **Saturation / LOS:** at Kathipara & T. Nagar, **degree of saturation 1.32–1.45** (up to **2.48** on the Guindy approach), **LOS E–F**, operating speeds as low as **1.5 km/h** in peak; free-flow ~25–28 km/h ([Frontiers 2025](https://www.frontiersin.org/journals/sustainable-cities/articles/10.3389/frsc.2025.1684489/full)).
- **Ambulance reality:** during peaks Indian-city ambulances crawl at **8–12 km/h**; simulations project **25–40%** travel-time saving with AI green corridors (vendor projection — treat as target, not measured) ([AIMCRS](https://www.aimcrs.com/)).
- **Road safety:** Chennai city **469 road deaths (2025), 519 (2024)**; NCRB ranks Chennai **highest metro for road deaths (5,034 in 2021)**; **motorcyclists 57% and pedestrians 34%** of fatalities, **64% of pedestrian crashes mid-block**; **104 identified black spots** (Kathipara, Koyambedu, Basin Bridge) ([DT Next 2025](https://www.dtnext.in/news/chennai/fatal-accidents-in-chennai-down-by-10-in-2025-says-police); [Madras Musings/NCRB](https://madrasmusings.com/vol-32-no-13/chennai-highest-in-number-of-road-accident-deaths-among-metros-ncrb-report/); [Citizen Matters](https://citizenmatters.in/chennai-speed-limit-road-accidents-traffic-police-gcc-gctp/); [DT Next black spots](https://www.dtnext.in/city/2022/09/08/104-black-spots-identified-in-chennai-steps-taken-to-reduce-deaths)). **Implication:** high mid-block pedestrian fatality share means the pedestrian-clearance floor must be preserved during preemption (catalog FSM-5).

## 3. Signal & ITS infrastructure — the integration target (CITS)

The **Chennai Intelligent Transport System (CITS)** is the system to integrate against, and it is being commissioned right now:

- **Funding/scope:** ₹530 cr implementation (₹645.59 cr project), **JICA loan**, Centre approved ₹530 cr **Jun 2026** ([Outlook/PTI](https://www.outlookindia.com/national/centre-approves-rs-530-cr-for-intelligent-transport-system-in-chennai-2)). **Contractor L&T**, agency **Chennai Smart City Ltd (CSCL)** ([Construction World](https://www.constructionworld.in/policy-updates-and-economic-news/centre-approves-chennai-intelligent-transport-system/93786)).
- **Scope:** **adaptive control at 165 junctions**, incident detection at 58, VMS at 17, red-light detection at 50 ([Construction World](https://www.constructionworld.in/policy-updates-and-economic-news/centre-approves-chennai-intelligent-transport-system/93786)).
- **Status:** civil work done at **104/165 junctions (Mar 2026)**, pilot at 17 sites since Jan 2024, **full operation targeted Aug 2026** — a live window to influence the preemption API ([Construction World](https://www.constructionworld.in/policy-updates-and-economic-news/centre-approves-chennai-intelligent-transport-system/93786)).
- **How it works:** replaces fixed 60–90 s cycles with demand-responsive **30–120 s** green; each junction = approach sensors + AI cameras (classify cars/buses/two-wheelers/pedestrians) + a **local control unit**; data feeds **Greater Chennai Traffic Police HQ, Vepery** which coordinates corridor-wide green waves ([Telangana Today/IANS](https://telanganatoday.com/chennai-to-roll-out-ai-powered-adaptive-traffic-signals-at-165-junctions)).
- **★ The hook:** CITS is "fully automated but includes **manual override … during emergencies, such as the passage of ambulances or VIP convoys**." Our project **automates this existing manual pathway** — the cleanest "Mode A = request into CITS" story ([Telangana Today/IANS](https://telanganatoday.com/chennai-to-roll-out-ai-powered-adaptive-traffic-signals-at-165-junctions)).
- **Existing look-ahead:** the current ITMS green-corridor design already gives "**green at three consecutive junctions ahead**" for ambulances/VVIPs — i.e., the **3-junction horizon our model uses is exactly Chennai's operating pattern** ([Transport in Chennai](https://en.wikipedia.org/wiki/Transport_in_Chennai)).
- **CITS Phase-1 corridors:** **Anna Salai, Jawaharlal Nehru Salai (Inner Ring Rd), Sardar Patel Rd, Kamarajar Salai, Rajaji Salai, Taylors Rd**, plus **EVR Salai** (6 pilot junctions incl. Vepery, Ega Theatre) — the first adaptive-ready set and the natural pilot corridors ([Telangana Today/IANS](https://telanganatoday.com/chennai-to-roll-out-ai-powered-adaptive-traffic-signals-at-165-junctions)).
- **Actuation layer already exists:** the Smart City **ICCC + ITMS** already fuses Police/Traffic/Transport feeds and controls adaptive signals — integrate into it rather than rebuild ([CSCL ITMS](https://cscl.co.in/intelligent-traffic-management-system); [Smart Cities ICCC](https://iccc.smartcities.gov.in/icc/city-details/e39a411b54c3ce46fd382fef7f632157)).
- **Open technical questions (verify with L&T/CSCL):** the adaptive **engine identity** (SCATS / SCOOT / indigenous **CoSiCoSt** by C-DAC — unconfirmed), and whether controllers speak **NTCIP 1202** vs a proprietary protocol (this determines the preemption API) ([C-DAC](https://www.cdac.in/index.aspx?id=products_services); [NTCIP](https://www.ntcip.org/actuated-signal-control-working-group/)).

## 4. Emergency-vehicle & healthcare ecosystem

- **108 service (GVK / EMRI Green Health Services):** ~**946 TAEI ambulances** statewide; **Chennai average response time 7.54 min** (2024, vs 13.22 min statewide) — traffic is the named bottleneck ([eHealth/Elets](https://ehealth.eletsonline.com/2024/12/emri-green-health-services-pilots-real-time-tracking-and-automated-ambulance-dispatch-in-tamil-nadu/); [DT Next 2023](https://www.dtnext.in/news/tamilnadu/overall-response-time-of-108-ambulances-drops-in-last-one-year-727237)). **A real-time GPS + automated nearest-ambulance dispatch pilot began Dec 2024** — the telemetry/AVLS layer our trigger needs already exists ([eHealth/Elets](https://ehealth.eletsonline.com/2024/12/emri-green-health-services-pilots-real-time-tracking-and-automated-ambulance-dispatch-in-tamil-nadu/)).
- **Hospital destinations (with areas):** RGGGH Park Town/Central (~13.081, 80.277; first full ED); Stanley, Royapuram (north); **Kilpauk MC — Level II trauma, "zero-delay ward"** (north-central); Omandurar super-speciality on Anna Salai (central); Institute of Child Health, Egmore (paediatric); Apollo Greams Rd (central); MIOT Manapakkam (west); Fortis Malar Adyar (south); SRMC / Sri Ramachandra Porur (west) ([RGGGH](https://en.wikipedia.org/wiki/Rajiv_Gandhi_Government_General_Hospital); [Kilpauk MC](https://en.wikipedia.org/wiki/Kilpauk_Medical_College); [Healthcare in Chennai](https://en.wikipedia.org/wiki/Healthcare_in_Chennai)). The spread (central/north/south/west) means corridors must span the whole metro.
- **Green-corridor precedent (proof + benchmark):** Chennai was the **first Indian city** to run one — the 2014 **GGH→Fortis Malar, ~12 km in 13 min 22 s vs ~45 min** (~70% cut); Apollo Teynampet→Frontier Mogappair ~11 min; extended to **Metro rail (2025)** and **multi-modal air+metro (Feb 2026)** ([Governance Now](https://www.governancenow.com/news/regular-story/chennai-police-sets-bar-high-green-corridor-initiative); [Kauvery](https://www.kauveryhospital.com/kauverian-scientific-journal/ready-steady-go-a-brief-on-green-corridor-activation-in-organ-transplantation/); [Expressnews Feb 2026](https://expressnews.asia/2026/02/apollo-hospitals-chennai-facilitates-three-life-saving-organ-transfers-in-a-single-day-through-road-and-metro-green-corridors/)). **~65–75% travel-time reduction** is the empirical ceiling to benchmark against.
- **Golden hour:** Tamil Nadu roughly **halved road deaths (~17k→~9k, 2016→2023)** via golden-hour care; only ~20% of victims nationally reach care within 60 min ([HHR Journal](https://www.hhrjournal.org/2025/09/30/saving-time-saving-lives-the-golden-hour-as-a-constitutional-guarantee-in-india/)).
- **Governance chain:** TN Health/EMRI **ERC** (dispatch + police/fire coordination) → **Greater Chennai Traffic Police** (route clearance, on-road executor) → **TRANSTAN** triggers organ corridors; Metro/airport for multi-modal ([TNHSP](https://tnhsp.org/tnhsp/108-emergency-ambulance-services.php); [Governance Now](https://www.governancenow.com/news/regular-story/chennai-police-sets-bar-high-green-corridor-initiative)).

## 5. Public transport, rail & governance

- **MTC buses:** ~**3,400–3,800** buses, ~**3.5 million riders/day**, **100% GPS-tracked via the Chalo "Chennai Bus" app** — a proven city-wide AVL model to ingest (and a template for emergency-vehicle GPS) ([MTC Wikipedia](https://en.wikipedia.org/wiki/Metropolitan_Transport_Corporation_(Chennai)); [Chalo](https://chalo.com/chennai)). No confirmed operational bus-priority lanes (so no competing signal-priority scheme).
- **Chennai Metro:** Phase 1 **54.1 km / 41 stations**; Phase 2 **118.9 km / 128 stations** opening in phases from 2026 — **grade-separated, so no surface conflict** ([Chennai Metro](https://en.wikipedia.org/wiki/Chennai_Metro)).
- **Rail level crossings (the one hard local override):** rail-gate closure physically overrides any green corridor. Chennai has aggressively grade-separated — **12 crossings closed in 2025–26**, Pallavaram–Tambaram now a road-under-bridge, MRTS fully elevated — so **active at-grade conflicts in the core are few but must be tracked**. No authoritative count of *remaining* metro-area crossings exists (data gap) ([New Indian Express/Verified](https://community.verified.realestate/article/chennai-division-closes-12-level-crossing-gates-in-2025-26-to-improve-railway-safety/); [Rail Analysis](https://news.railanalysis.com/southern-railway-completely-eliminates-unmanned-and-manned-level-crossings-in-tamil-nadu/)). **The backend must keep a live crossing registry and treat "gate closing/closed" as an un-preemptible top-priority block.**
- **Governance owner = CUMTA** — statutory (Act 2010, amended 2020/21), **CM-chaired**, jurisdiction the whole 5,904 sq km metro; the only body that can authorize cross-agency preemption. It is building **Chennai One** (unified app + planned common road-asset database) with an **Open Innovation Challenge** as an entry channel ([CUMTA](https://www.cumta.tn.gov.in/); [CUMTA Act](https://www.indiacode.nic.in/bitstream/123456789/13110/1/cumta_act.pdf); [Open Innovation](https://cumta.tn.gov.in/openinnovationchallenge/)).
- **Road ownership is fragmented:** GCC (city roads), TN Highways Dept (arterials incl. Anna Salai), NHAI (GST Rd/NH-32), with GCTP operating the signals — CUMTA is the unifying layer to deploy under ([GCC Roads](https://www.chennaicorporation.gov.in/departments/roads/index.htm)).

---

## 6. Calibration — turning the study into backend config

These are the area-specific values to seed the backend's `config.yaml` and integration design (pair with the universal safety rules in `Green_Corridor_Requirements_Catalog.md`).

**Priority corridors (build order).** Start where CITS is adaptive-ready *and* hospital-linked: **EVR Periyar Salai** (highest hospital density + 6 live pilot junctions — best first pilot), then **Anna Salai** (Omandurar + Apollo + central spine), then **Inner Ring Rd / JN Salai** (cross-town to MIOT/Porur and to north hospitals). These are exactly CITS Phase-1 corridors.

**Progression speed for offsets** (offset = link_length ÷ speed):
- Peak (AM 08:00–10:30, PM 17:00–20:00): **~4.5 m/s (~16 km/h)**; evening worst-case floor **~4 m/s (~14.6 km/h)**.
- Off-peak: **~7 m/s (~25 km/h)**.
- Ambulance base cruise in traffic: **~3 m/s (~11 km/h)** peak — size the look-ahead arming window from this.

**Preemption priority order (hard, Chennai-specific at the top):**
1. **Rail level-crossing gate closed** → un-preemptible hard block (live registry).
2. Code Red emergency (life-threatening).
3. Code Blue emergency.
4. Transit/adaptive normal (CITS default).
(Railroad-over-everything mirrors the universal catalog ARB-1; the rest is our EV logic.)

**Integration path (Mode A).** Target the **CITS/ICCC adaptive-signal layer** via **L&T (SI) / CSCL (authority)**, with **GCTP Vepery HQ as the TMC/server host** and **CUMTA as the governing sponsor**. Automate the *already-designed* manual ambulance override. Keep **Mode B** (drive lamps under an independent monitor) as the fallback for non-CITS junctions. Resolve the **NTCIP-1202-vs-proprietary** question early — it dictates the API. → **[superseded 2026-07-03: Mode B is the default everywhere; Mode A deferred to end stage]**

**Telemetry source.** Ingest the **108/EMRI GPS + auto-dispatch** feed as the preemption trigger (with the catalog's SEC-5/6 plausibility gating, since dense-city GPS is noisy); model **MTC Chalo GPS** vehicles as background/priority-yielding traffic.

**Saturation & pedestrian model.** Use **PCU-based saturation flow with two-wheeler front-loading**, not HCM defaults; **preserve pedestrian clearance** at retail junctions (T. Nagar-type) given the 34% pedestrian / 64%-mid-block fatality share.

**Junctions to instrument/model first:** Kathipara, T. Nagar/Panagal Park, Koyambedu/Maduravoyal, Gemini/Teynampet — highest saturation *and* black spots (max benefit, hardest clearance). Enumerate **river-bridge choke-crossings** (Cooum/Adyar) as mandatory route nodes.

**KPI baselines (for the business case & tests):** beat the **7.54 min** Chennai 108 response time; target the vendor-projected **25–40%** on-road reduction; the proven organ-corridor benchmark is **~45 min → ~13 min over ~12 km (~70%)**; addressable trauma load ~**470–520 road deaths/yr** in the city.

## 7. Data gaps to close with primary stakeholders

- CITS adaptive **engine identity** and **controller protocol** (NTCIP vs proprietary) — from L&T/CSCL. Determines the preemption API. → **[deferred to end stage]**
- **Citywide signalised-junction count** (165 is the CITS set only; city total is larger) — from GCTP.
- **Remaining active rail level crossings** inside the metro area — from Southern Railway Chennai Division / GCC Bridges Dept (needed for the un-preemptible registry).
- **Per-corridor speed/queue/saturation** and **junction geometry + crossing distances** — from CITS sensor data / a short field study (sets offsets, min-green, ped floors).
- **Hospital ambulance-call density / accident hotspot maps** — from 108/EMRI + GCTP (sets corridor rollout order).

---

## Sources

Roads & geography
- [GCC Roads Department](https://chennaicorporation.gov.in/gcc/department/road/) · [GCC Bridges Dept](https://chennaicorporation.gov.in/gcc/department/bridges/) · [Anna Salai](https://en.wikipedia.org/wiki/Anna_Salai) · [EVR Periyar Salai](https://en.wikipedia.org/wiki/EVR_Periyar_Salai) · [Rajiv Gandhi Salai/OMR](https://en.wikipedia.org/wiki/Rajiv_Gandhi_Salai) · [GST Road](https://en.wikipedia.org/wiki/Grand_Southern_Trunk_Road) · [Inner Ring Road](https://en.wikipedia.org/wiki/Inner_Ring_Road,_Chennai) · [Outer Ring Road (CMDA)](https://cmdachennai.gov.in/outerringroad.html) · [Kathipara Junction](https://en.wikipedia.org/wiki/Kathipara_Junction) · [Flyovers in Chennai](https://en.wikipedia.org/wiki/Flyovers_in_Chennai) · [Geography of Chennai](https://en.wikipedia.org/wiki/Geography_of_Chennai) · [CMDA Master Plan](https://www.cmdachennai.gov.in/smp_main.html) · [OSM India (Geofabrik)](https://download.geofabrik.de/asia/india.html)

Traffic & safety
- [Frontiers in Sustainable Cities 2025 — Kathipara & T. Nagar study](https://www.frontiersin.org/journals/sustainable-cities/articles/10.3389/frsc.2025.1684489/full) · [TomTom Traffic Index — Chennai](https://www.tomtom.com/traffic-index/city/chennai) · [Transport in Chennai](https://en.wikipedia.org/wiki/Transport_in_Chennai) · [PLOS One 2024 — saturation flow, non-lane-based](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0306112) · [DT Next — Chennai fatalities 2025](https://www.dtnext.in/news/chennai/fatal-accidents-in-chennai-down-by-10-in-2025-says-police) · [NCRB via Madras Musings](https://madrasmusings.com/vol-32-no-13/chennai-highest-in-number-of-road-accident-deaths-among-metros-ncrb-report/) · [Citizen Matters — VRU fatalities](https://citizenmatters.in/chennai-speed-limit-road-accidents-traffic-police-gcc-gctp/) · [DT Next — 104 black spots](https://www.dtnext.in/city/2022/09/08/104-black-spots-identified-in-chennai-steps-taken-to-reduce-deaths) · [AIMCRS — green-corridor projections](https://www.aimcrs.com/)

Signals & ITS (CITS)
- [Outlook/PTI — Centre approves ₹530 cr CITS](https://www.outlookindia.com/national/centre-approves-rs-530-cr-for-intelligent-transport-system-in-chennai-2) · [Construction World — CITS scope/status](https://www.constructionworld.in/policy-updates-and-economic-news/centre-approves-chennai-intelligent-transport-system/93786) · [Telangana Today/IANS — 165 adaptive junctions + ambulance override](https://telanganatoday.com/chennai-to-roll-out-ai-powered-adaptive-traffic-signals-at-165-junctions) · [CSCL ITMS](https://cscl.co.in/intelligent-traffic-management-system) · [Smart Cities ICCC — Chennai](https://iccc.smartcities.gov.in/icc/city-details/e39a411b54c3ce46fd382fef7f632157) · [C-DAC CoSiCoSt](https://www.cdac.in/index.aspx?id=products_services) · [NTCIP actuated signal WG](https://www.ntcip.org/actuated-signal-control-working-group/)

Emergency vehicles & healthcare
- [eHealth/Elets — EMRI real-time tracking & auto-dispatch (Dec 2024)](https://ehealth.eletsonline.com/2024/12/emri-green-health-services-pilots-real-time-tracking-and-automated-ambulance-dispatch-in-tamil-nadu/) · [DT Next — 108 response times](https://www.dtnext.in/news/tamilnadu/overall-response-time-of-108-ambulances-drops-in-last-one-year-727237) · [NHM TN — TAEI](https://www.nhm.tn.gov.in/en/node/6268) · [RGGGH](https://en.wikipedia.org/wiki/Rajiv_Gandhi_Government_General_Hospital) · [Kilpauk MC](https://en.wikipedia.org/wiki/Kilpauk_Medical_College) · [Healthcare in Chennai](https://en.wikipedia.org/wiki/Healthcare_in_Chennai) · [Governance Now — green corridor](https://www.governancenow.com/news/regular-story/chennai-police-sets-bar-high-green-corridor-initiative) · [Kauvery — green corridor](https://www.kauveryhospital.com/kauverian-scientific-journal/ready-steady-go-a-brief-on-green-corridor-activation-in-organ-transplantation/) · [Expressnews — multi-modal corridor Feb 2026](https://expressnews.asia/2026/02/apollo-hospitals-chennai-facilitates-three-life-saving-organ-transfers-in-a-single-day-through-road-and-metro-green-corridors/) · [HHR Journal — golden hour](https://www.hhrjournal.org/2025/09/30/saving-time-saving-lives-the-golden-hour-as-a-constitutional-guarantee-in-india/)

Transit, rail & governance
- [MTC (Wikipedia)](https://en.wikipedia.org/wiki/Metropolitan_Transport_Corporation_(Chennai)) · [Chalo Chennai](https://chalo.com/chennai) · [Chennai Metro](https://en.wikipedia.org/wiki/Chennai_Metro) · [Chennai Suburban Railway](https://en.wikipedia.org/wiki/Chennai_Suburban_Railway) · [Chennai MRTS](https://en.wikipedia.org/wiki/Chennai_Mass_Rapid_Transit_System) · [New Indian Express/Verified — 12 level crossings closed](https://community.verified.realestate/article/chennai-division-closes-12-level-crossing-gates-in-2025-26-to-improve-railway-safety/) · [Rail Analysis — TN level-crossing elimination](https://news.railanalysis.com/southern-railway-completely-eliminates-unmanned-and-manned-level-crossings-in-tamil-nadu/) · [CUMTA](https://www.cumta.tn.gov.in/) · [CUMTA Act 2010](https://www.indiacode.nic.in/bitstream/123456789/13110/1/cumta_act.pdf) · [CUMTA Open Innovation Challenge](https://cumta.tn.gov.in/openinnovationchallenge/)

*Caveats: fleet-mix percentages are 2012–13 vintage (structurally stable); NCRB metro deaths and GCC city-limit deaths use different geographies; CITS adaptive-engine identity and controller protocol are unconfirmed; the count of remaining active metro-area rail crossings and the citywide signal count were not found in authoritative sources; vendor time-saving projections (25–40%) are unvalidated targets.*
