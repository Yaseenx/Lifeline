// Live "hospitals near the vehicle" from OpenStreetMap via the Overpass API
// (free, no key — same pattern as signals.ts). This gives COVERAGE: every
// mapped hospital around the GPS position. It cannot give TRUST: OSM's
// emergency=* tag is sparsely applied in India, so results are merged with the
// curated verified list in hospitals.ts, verified entries are always kept and
// labelled, and anything explicitly tagged emergency=no is dropped.

import { Hospital, HOSPITALS, registerHospitals } from './hospitals'

// Public Overpass mirrors, tried in order — the main one is often busy.
const ENDPOINTS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://overpass.private.coffee/api/interpreter',
]

const RADIUS_M = 8000 // search radius around the vehicle
const MAX_ELEMENTS = 80 // cap what we ask Overpass for
const DEDUPE_M = 150 // live entry this close to a verified one = same hospital

type LatLng = { lat: number; lng: number }

// --- geo helper (meters) ---
const Re = 6371000
const toRad = (d: number) => (d * Math.PI) / 180
function distanceM(a: LatLng, b: LatLng) {
  const dLat = toRad(b.lat - a.lat)
  const dLng = toRad(b.lng - a.lng)
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2
  return 2 * Re * Math.asin(Math.sqrt(h))
}

interface OverpassElement {
  type: 'node' | 'way' | 'relation'
  id: number
  lat?: number
  lon?: number
  center?: { lat: number; lon: number }
  tags?: Record<string, string>
}

const MIRROR_TIMEOUT_MS = 10000 // a hung mirror must not stall the list forever

// ---------------------------------------------------------------------------
// PRIMARY source: Google Places (New) Nearby Search — the same coverage you
// see in Google Maps' "hospitals near me". Uses the dashboard's existing Maps
// key; requires "Places API (New)" to be enabled on it. Google doesn't expose
// emergency-department status, so results are 'unknown' ED — listed, but never
// auto-suggested for an emergency (the verified tier handles that).
// ---------------------------------------------------------------------------
const GOOGLE_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined
const GOOGLE_TIMEOUT_MS = 8000

interface GPlace {
  id: string
  displayName?: { text?: string }
  location?: { latitude: number; longitude: number }
}

export async function fetchHospitalsGoogle(lat: number, lng: number): Promise<Hospital[]> {
  if (!GOOGLE_KEY) throw new Error('no Google API key configured')
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), GOOGLE_TIMEOUT_MS)
  try {
    const res = await fetch('https://places.googleapis.com/v1/places:searchNearby', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': GOOGLE_KEY,
        'X-Goog-FieldMask': 'places.id,places.displayName,places.location',
      },
      body: JSON.stringify({
        includedTypes: ['hospital'],
        maxResultCount: 20,
        rankPreference: 'DISTANCE',
        locationRestriction: {
          circle: { center: { latitude: lat, longitude: lng }, radius: RADIUS_M },
        },
      }),
      signal: ctrl.signal,
    })
    if (!res.ok) throw new Error(`Places HTTP ${res.status} (enable "Places API (New)" for this key?)`)
    const data = await res.json()
    const places = (data.places ?? []) as GPlace[]
    return places
      .filter((p) => p.location && p.displayName?.text)
      .map((p) => ({
        id: `gplace-${p.id}`,
        name: p.displayName!.text!,
        lat: p.location!.latitude,
        lng: p.location!.longitude,
        emergency: 'unknown' as const,
      }))
  } finally {
    clearTimeout(timer)
  }
}

// Query Overpass, trying each mirror until one returns valid JSON.
async function queryOverpass(query: string): Promise<OverpassElement[]> {
  let lastErr: unknown
  for (const url of ENDPOINTS) {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), MIRROR_TIMEOUT_MS)
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ data: query }).toString(),
        signal: ctrl.signal,
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      // A busy server returns an HTML error page, not JSON.
      const text = await res.text()
      if (!text.trimStart().startsWith('{')) throw new Error('server busy')
      const data = JSON.parse(text)
      return data.elements ?? []
    } catch (e) {
      lastErr = e
      console.warn('[hospitals] mirror failed:', url, e instanceof Error ? e.message : e)
    } finally {
      clearTimeout(timer)
    }
  }
  throw new Error(lastErr instanceof Error ? lastErr.message : 'Overpass unavailable')
}

// Backup tier so "nearby" is never empty in Chennai when Overpass is down:
// CMCHIS-empanelled Chennai-district hospitals (tn.data.gov.in NK48 list,
// updated 2026-06-25) that are not already in the verified registry.
// Government-supplied coordinates — approximate; ED status unknown, so these
// are never auto-suggested for an emergency (conservative).
export const FALLBACK_HOSPITALS: Hospital[] = [
  { id: 'cmchis-chennai-national', name: 'Chennai National Hospital (CMCHIS L1)', lat: 13.09646, lng: 80.29166, emergency: 'unknown' },
  { id: 'cmchis-apollo-tondiarpet', name: 'Apollo Hospitals, Tondiarpet (CMCHIS L2)', lat: 13.12893, lng: 80.29056, emergency: 'unknown' },
  { id: 'cmchis-mehta-chetpet', name: "Dr Mehta's Hospitals, Chetpet (CMCHIS L2)", lat: 13.07154, lng: 80.24051, emergency: 'unknown' },
  { id: 'cmchis-bharathirajaa', name: 'Bharathirajaa Speciality, T. Nagar (CMCHIS L2)', lat: 13.04816, lng: 80.24505, emergency: 'unknown' },
  { id: 'cmchis-venkataeswara', name: 'Venkataeswara Hospital, Nandanam (CMCHIS L2)', lat: 13.0301, lng: 80.24142, emergency: 'unknown' },
  { id: 'cmchis-vhs-taramani', name: 'Voluntary Health Services, Taramani (CMCHIS L2)', lat: 13.00427, lng: 80.24728, emergency: 'unknown' },
  { id: 'cmchis-prashanth-velachery', name: 'Prashanth Hospital, Velachery (CMCHIS L2)', lat: 12.97833, lng: 80.22126, emergency: 'unknown' },
  { id: 'cmchis-promed-kottivakkam', name: 'Promed Hospital, Kottivakkam (CMCHIS L1)', lat: 12.96922, lng: 80.25861, emergency: 'unknown' },
  { id: 'cmchis-pride', name: 'Pride Super Specialty Hospital (CMCHIS L3)', lat: 13.10339, lng: 80.26765, emergency: 'unknown' },
  { id: 'cmchis-gph-periyar-nagar', name: 'Govt Peripheral Hospital, Periyar Nagar (CMCHIS L3)', lat: 13.11527, lng: 80.2239, emergency: 'unknown' },
  { id: 'cmchis-gph-tondiarpet', name: 'Govt Peripheral Hospital, Tondiarpet (CMCHIS L3)', lat: 13.12602, lng: 80.28669, emergency: 'unknown' },
]

const normName = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '')

// Every named hospital mapped within RADIUS_M of the position.
export async function fetchHospitalsAround(lat: number, lng: number): Promise<Hospital[]> {
  const query =
    `[out:json][timeout:25];` +
    `nwr["amenity"="hospital"](around:${RADIUS_M},${lat},${lng});` +
    `out center ${MAX_ELEMENTS};`

  const elements = await queryOverpass(query)

  const out: Hospital[] = []
  const seenNames = new Set<string>()
  for (const el of elements) {
    const plat = el.lat ?? el.center?.lat
    const plng = el.lon ?? el.center?.lon
    if (plat == null || plng == null) continue
    const tags = el.tags ?? {}
    const name = tags.name || tags['name:en']
    if (!name) continue // unnamed entries aren't actionable for a driver
    if (tags.emergency === 'no') continue // explicitly no emergency dept
    const key = normName(name)
    if (seenNames.has(key)) continue // same hospital mapped as node + building
    seenNames.add(key)
    out.push({
      id: `osm-${el.type}-${el.id}`,
      name,
      lat: plat,
      lng: plng,
      emergency: tags.emergency === 'yes' ? 'yes' : 'unknown',
    })
  }
  return out
}

// Merge live results with the curated verified list, compute distances from
// the vehicle, sort nearest-first, and register everything for id resolution.
export function mergeHospitals(live: Hospital[], origin: LatLng): Hospital[] {
  const merged: Hospital[] = HOSPITALS.map((h) => ({ ...h }))
  for (const h of live) {
    const dup = merged.some(
      (m) => distanceM(m, h) < DEDUPE_M || normName(m.name) === normName(h.name),
    )
    if (!dup) merged.push({ ...h })
  }
  for (const m of merged) m.distKm = distanceM(origin, m) / 1000
  merged.sort((a, b) => (a.distKm ?? Infinity) - (b.distKm ?? Infinity))
  registerHospitals(merged)
  return merged
}
