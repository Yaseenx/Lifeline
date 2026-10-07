// Hospital destinations. Two tiers:
//   1. VERIFIED (below) — curated, emergency-verified hospitals. Always shown.
//   2. LIVE — every mapped hospital near the vehicle's GPS, fetched at runtime
//      from OpenStreetMap (see hospitalsLive.ts) and merged with this list.
// The map alone cannot prove a hospital is emergency-equipped (OSM's
// emergency=* tag is sparse in India), so verified entries are labelled and
// preferred. TODO: replace the curated tier with the server's hospital
// registry (108/EMRI + TN Health empanelled list) once the backend exists.

export interface Hospital {
  id: string
  name: string
  lat: number
  lng: number
  verified?: boolean                     // on the curated emergency-verified list
  emergency?: 'yes' | 'no' | 'unknown'   // OSM emergency tag (live entries)
  specialty?: 'paediatric' | 'obgyn' | 'cardiac'  // specialty-only ED — not a general (adult) ED
  distKm?: number                        // distance from the vehicle (set at merge)
}

// Coordinates from the curated capability registry (chennai-hospitals.json,
// Google-place-ID geocoded) — see docs/Chennai_Hospital_Capability_Study.md.
export const HOSPITALS: Hospital[] = [
  { id: 'apollo-greams-road', name: 'Apollo Hospitals, Greams Road', lat: 13.0631824, lng: 80.2515375, verified: true, emergency: 'yes' },
  { id: 'miot-international', name: 'MIOT International, Manapakkam', lat: 13.0213892, lng: 80.1857828, verified: true, emergency: 'yes' },
  { id: 'gleneagles-global-health-city', name: 'Gleneagles Global Health City, Perumbakkam', lat: 12.8978488, lng: 80.2061841, verified: true, emergency: 'yes' },
  { id: 'mgm-healthcare', name: 'MGM Healthcare, Aminjikarai', lat: 13.0709761, lng: 80.2216656, verified: true, emergency: 'yes' },
  { id: 'kauvery-alwarpet', name: 'Kauvery Hospital, Alwarpet', lat: 13.038238, lng: 80.2571361, verified: true, emergency: 'yes' },
  { id: 'sims-vadapalani', name: 'SIMS Hospital, Vadapalani', lat: 13.0516924, lng: 80.2117546, verified: true, emergency: 'yes' },
  { id: 'srmc-porur', name: 'Sri Ramachandra Medical Centre, Porur', lat: 13.0391373, lng: 80.1434689, verified: true, emergency: 'yes' },
  { id: 'rela-chromepet', name: 'Dr. Rela Institute, Chromepet', lat: 12.9549235, lng: 80.1388459, verified: true, emergency: 'yes' },
  { id: 'mgm-malar-adyar', name: 'MGM Malar (ex-Fortis), Adyar', lat: 13.0101544, lng: 80.258616, verified: true, emergency: 'yes' },
  { id: 'madras-medical-mission', name: 'Madras Medical Mission, Mogappair', lat: 13.0859697, lng: 80.187141, verified: true, emergency: 'yes' },
  { id: 'frontier-lifeline', name: 'Frontier Lifeline (cardiac), Mogappair', lat: 13.087721, lng: 80.185609, verified: true, emergency: 'yes', specialty: 'cardiac' },
  { id: 'rgggh-mmc', name: 'Rajiv Gandhi Govt. General Hospital (MMC)', lat: 13.0814162, lng: 80.2775787, verified: true, emergency: 'yes' },
  { id: 'stanley-mch', name: 'Govt. Stanley Medical College Hospital', lat: 13.1059369, lng: 80.2852016, verified: true, emergency: 'yes' },
  { id: 'kilpauk-mch', name: 'Govt. Kilpauk Medical College Hospital', lat: 13.0783427, lng: 80.2438901, verified: true, emergency: 'yes' },
  { id: 'royapettah-gh', name: 'Govt. Royapettah Hospital', lat: 13.0552786, lng: 80.2648512, verified: true, emergency: 'yes' },
  { id: 'kalaignar-kcssh-guindy', name: 'Kalaignar Centenary Super Speciality, Guindy', lat: 13.0151079, lng: 80.2155023, verified: true, emergency: 'yes' },
  { id: 'tngmssh-omandurar', name: 'TN Govt Multi Super Speciality, Omandurar', lat: 13.0691876, lng: 80.2737108, verified: true, emergency: 'yes' },
  { id: 'ich-egmore', name: 'Institute of Child Health, Egmore (paediatric)', lat: 13.07349, lng: 80.2569271, verified: true, emergency: 'yes', specialty: 'paediatric' },
  { id: 'iog-egmore', name: 'Institute of Obstetrics & Gynaecology, Egmore', lat: 13.0714838, lng: 80.2589166, verified: true, emergency: 'yes', specialty: 'obgyn' },
]

export const DEFAULT_HOSPITAL = HOSPITALS[0]

// Registry so any component (map, routing hooks) can resolve a destination id,
// including live OSM hospitals discovered after startup.
const registry = new Map<string, Hospital>(HOSPITALS.map((h) => [h.id, h]))

export function registerHospitals(list: Hospital[]) {
  for (const h of list) registry.set(h.id, h)
}

export function resolveHospital(id: string | null | undefined): Hospital | undefined {
  return id ? registry.get(id) : undefined
}

// Known emergency department: every verified-tier hospital has one; live OSM
// entries only when explicitly tagged emergency=yes. 'unknown' is treated as
// NO for emergency routing (conservative — a Code Red must not gamble).
export function hasEmergencyDept(h: Hospital): boolean {
  return !!h.verified || h.emergency === 'yes'
}

// A GENERAL (adult) emergency department. Excludes specialty-only hospitals
// (paediatric, OB/GYN, cardiac), which must not be auto-suggested as the nearest
// ED for an undifferentiated Code Red — they stay selectable manually.
export function isGeneralEmergencyDept(h: Hospital): boolean {
  return hasEmergencyDept(h) && !h.specialty
}

// Great-circle distance in km.
export function distanceKm(aLat: number, aLng: number, bLat: number, bLng: number) {
  const R = 6371
  const toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(bLat - aLat)
  const dLng = toRad(bLng - aLng)
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

// Closest hospital to a given position (straight-line distance).
export function nearestHospital(
  lat: number,
  lng: number,
  list: Hospital[] = HOSPITALS,
): { hospital: Hospital; km: number } {
  let best = list[0]
  let bestKm = Infinity
  for (const h of list) {
    const km = distanceKm(lat, lng, h.lat, h.lng)
    if (km < bestKm) {
      bestKm = km
      best = h
    }
  }
  return { hospital: best, km: bestKm }
}
