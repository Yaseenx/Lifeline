// Traffic signals along a route, from OpenStreetMap via the Overpass API
// (free, no key). We fetch traffic_signals nodes in the route's bounding box,
// keep those that sit on the route, and tag each with its distance-along-route.

export type LatLng = { lat: number; lng: number }
export interface RouteSignal {
  lat: number
  lng: number
  distAlong: number // meters from route start
}

// Public Overpass mirrors, tried in order — the main one is often busy.
const ENDPOINTS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://overpass.private.coffee/api/interpreter',
]
const MAX_OFFSET_M = 45 // how close to the route a signal must be to count
const MERGE_M = 25 // collapse signals clustered at the same junction

// --- geo helpers (meters) ---
const Re = 6371000
const toRad = (d: number) => (d * Math.PI) / 180

function distance(a: LatLng, b: LatLng) {
  const dLat = toRad(b.lat - a.lat)
  const dLng = toRad(b.lng - a.lng)
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2
  return 2 * Re * Math.asin(Math.sqrt(h))
}

function projectOnSegment(p: LatLng, a: LatLng, b: LatLng) {
  const k = Math.cos(toRad(a.lat))
  const bx = (b.lng - a.lng) * k
  const by = b.lat - a.lat
  const px = (p.lng - a.lng) * k
  const py = p.lat - a.lat
  const len2 = bx * bx + by * by || 1e-12
  let t = (px * bx + py * by) / len2
  t = Math.max(0, Math.min(1, t))
  return { lat: a.lat + t * (b.lat - a.lat), lng: a.lng + t * (b.lng - a.lng) }
}

function cumulative(path: LatLng[]) {
  const cum = [0]
  for (let i = 1; i < path.length; i++) cum[i] = cum[i - 1] + distance(path[i - 1], path[i])
  return cum
}

// Query Overpass, trying each mirror until one returns valid JSON.
async function queryOverpass(query: string): Promise<{ lat: number; lon: number }[]> {
  let lastErr: unknown
  for (const url of ENDPOINTS) {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ data: query }).toString(),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      // A busy server returns an HTML error page, not JSON.
      const text = await res.text()
      if (!text.trimStart().startsWith('{')) throw new Error('server busy')
      const data = JSON.parse(text)
      return (data.elements ?? []).filter((e: { type: string }) => e.type === 'node')
    } catch (e) {
      lastErr = e
    }
  }
  throw new Error(lastErr instanceof Error ? lastErr.message : 'Overpass unavailable')
}

export async function fetchSignalsAlongRoute(path: LatLng[]): Promise<RouteSignal[]> {
  if (path.length < 2) return []

  let south = Infinity
  let west = Infinity
  let north = -Infinity
  let east = -Infinity
  for (const p of path) {
    south = Math.min(south, p.lat)
    north = Math.max(north, p.lat)
    west = Math.min(west, p.lng)
    east = Math.max(east, p.lng)
  }
  const pad = 0.002
  const query =
    `[out:json][timeout:25];` +
    `node["highway"="traffic_signals"](${south - pad},${west - pad},${north + pad},${east + pad});` +
    `out;`

  const nodes = await queryOverpass(query)

  const cum = cumulative(path)
  const found: RouteSignal[] = []
  for (const el of nodes) {
    const pt = { lat: el.lat, lng: el.lon }
    let best = Infinity
    let bestAlong = 0
    for (let i = 0; i < path.length - 1; i++) {
      const snap = projectOnSegment(pt, path[i], path[i + 1])
      const d = distance(pt, snap)
      if (d < best) {
        best = d
        bestAlong = cum[i] + distance(path[i], snap)
      }
    }
    if (best <= MAX_OFFSET_M) found.push({ lat: pt.lat, lng: pt.lng, distAlong: bestAlong })
  }

  found.sort((a, b) => a.distAlong - b.distAlong)
  const merged: RouteSignal[] = []
  for (const s of found) {
    if (!merged.length || s.distAlong - merged[merged.length - 1].distAlong > MERGE_M) merged.push(s)
  }
  return merged
}
