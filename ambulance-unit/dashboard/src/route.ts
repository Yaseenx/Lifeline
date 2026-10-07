// Road-following route geometry. Uses the public OSRM demo server, which is
// FREE and needs no API key or billing (Google's Routes/Directions APIs both
// require a billing-enabled key). Fine for demo/testing; for production swap in
// a self-hosted OSRM, OpenRouteService, or Google Routes API.
//
// Docs: https://project-osrm.org/docs/v5.24.0/api/

export type LatLng = { lat: number; lng: number }

// Fastest-route geometry plus its length and driving time (from OSRM).
export interface RouteInfo {
  coords: LatLng[]
  distanceM: number // total route length, metres
  durationS: number // OSRM's free-flow driving time, seconds
}

const BASE = 'https://router.project-osrm.org/route/v1/driving'

export async function computeRouteInfo(origin: LatLng, dest: LatLng): Promise<RouteInfo> {
  // OSRM expects lng,lat order.
  const coords = `${origin.lng},${origin.lat};${dest.lng},${dest.lat}`
  const url = `${BASE}/${coords}?overview=full&geometries=geojson`

  const res = await fetch(url)
  if (!res.ok) throw new Error(`Routing service ${res.status}: ${res.statusText}`)

  const data = await res.json()
  if (data.code !== 'Ok' || !data.routes?.[0]) {
    throw new Error(data.message || data.code || 'No route found.')
  }

  const r = data.routes[0]
  // GeoJSON LineString coordinates are [lng, lat].
  const line = r.geometry.coordinates as [number, number][]
  return {
    coords: line.map(([lng, lat]) => ({ lat, lng })),
    distanceM: Number(r.distance) || 0,
    durationS: Number(r.duration) || 0,
  }
}

export async function computeRoute(origin: LatLng, dest: LatLng): Promise<LatLng[]> {
  return (await computeRouteInfo(origin, dest)).coords
}
