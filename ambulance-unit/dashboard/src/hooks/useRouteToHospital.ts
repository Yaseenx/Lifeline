import { useEffect, useRef, useState } from 'react'
import type { VehicleState } from '../protocol'
import { resolveHospital } from '../hospitals'
import { computeRouteInfo, type LatLng } from '../route'
import { type RouteSignal } from '../signals'

// AGENT-MODE map overlay. The server owns the CONTROLLED junctions (the green
// corridor); this adds context the server doesn't compute:
//   • the fastest road route from the live GPS to the chosen hospital (OSRM),
//   • EVERY traffic signal along that route (OpenStreetMap, keyless),
//   • live remaining distance + fastest-route ETA (updates as you drive).
// All keyless. The driver still picks the hospital; this just visualises it.

const MIN_ETA_MPS = 3 // ETA floor: ~11 km/h Chennai peak, so a stopped unit still shows an ETA
const REROUTE_MOVE_M = 400 // re-run OSRM/Overpass only after the vehicle drifts this far
const PASS_MARGIN_M = 25 // a signal this far behind the vehicle counts as 'passed'
const GRANT_LOOKAHEAD_M = 400 // signals within this distance ahead are being cleared (green)

// A live on-route signal with its green-wave state relative to the vehicle.
export interface RouteSignalState {
  lat: number
  lng: number
  distAlong: number
  state: 'passed' | 'granted' | 'requested'
  eta_sec: number
}

export interface RouteToHospital {
  path: LatLng[]
  signals: RouteSignalState[]
  distanceM: number | null
  etaSec: number | null
  loading: boolean
  note: string | null
}

// --- geo helpers (metres) ---
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
function cumulative(path: LatLng[]) {
  const cum = [0]
  for (let i = 1; i < path.length; i++) cum[i] = cum[i - 1] + distance(path[i - 1], path[i])
  return cum
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
function distAlong(path: LatLng[], cum: number[], p: LatLng) {
  let best = Infinity
  let along = 0
  for (let i = 0; i < path.length - 1; i++) {
    const snap = projectOnSegment(p, path[i], path[i + 1])
    const d = distance(p, snap)
    if (d < best) {
      best = d
      along = cum[i] + distance(path[i], snap)
    }
  }
  return along
}

export function useRouteToHospital(state: VehicleState | null): RouteToHospital {
  const [path, setPath] = useState<LatLng[]>([])
  const [signals, setSignals] = useState<RouteSignal[]>([])
  const [loading, setLoading] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const cumRef = useRef<number[]>([])
  const keyRef = useRef<string>('') // destination id currently routed to
  const anchor = useRef<LatLng | null>(null) // where the current route was computed

  const trip = state?.trip
  // The route target depends on the leg. Leg 1 = drive to the ACCIDENT / pickup
  // (origin comes from the dispatch); leg 2 = transport to the chosen hospital.
  const onLeg1 = !!trip?.active && trip.leg === 1 && trip.origin_lat != null && trip.origin_lng != null
  const active = !!trip?.active && (onLeg1 || trip.leg !== 1)
  const destId = trip?.destination_id ?? null
  const dest = !active
    ? undefined
    : onLeg1
      ? { lat: trip!.origin_lat as number, lng: trip!.origin_lng as number, id: 'scene', name: trip!.origin_address || 'Accident scene' }
      : resolveHospital(destId)
  const destKey = onLeg1 ? `scene:${trip?.origin_lat},${trip?.origin_lng}` : `h:${destId ?? ''}`
  const lat = state?.lat
  const lng = state?.lng
  const gpsOk = !!state?.gps_fix && lat != null && lng != null && !(lat === 0 && lng === 0)

  // Recompute the road route + signals when the destination changes or the
  // vehicle has drifted far from where the last route was planned.
  const gridLat = lat != null ? Math.round(lat * 250) / 250 : 0
  const gridLng = lng != null ? Math.round(lng * 250) / 250 : 0
  useEffect(() => {
    if (!active || !dest || !gpsOk || lat == null || lng == null) {
      setPath([])
      setSignals([])
      setNote(null)
      keyRef.current = ''
      anchor.current = null
      return
    }
    const here: LatLng = { lat, lng }
    const moved = anchor.current ? distance(anchor.current, here) : Infinity
    if (destKey === keyRef.current && moved < REROUTE_MOVE_M) return // still fresh
    keyRef.current = destKey
    anchor.current = here

    let cancelled = false
    setLoading(true)
    ;(async () => {
      try {
        const info = await computeRouteInfo(here, { lat: dest.lat, lng: dest.lng })
        if (cancelled) return
        setPath(info.coords)
        cumRef.current = cumulative(info.coords)
        // Signals come from the SERVER corridor (state.corridor.nodes) now — the
        // browser no longer calls Overpass. This path is only a fallback line for
        // the brief moment before the server corridor arrives.
        setSignals([])
        setNote(null)
      } catch {
        if (cancelled) return
        const straight = [here, { lat: dest.lat, lng: dest.lng }]
        setPath(straight)
        cumRef.current = cumulative(straight)
        setSignals([])
        setNote('Routing service unavailable — straight line shown.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, destKey, gpsOk, gridLat, gridLng])

  // Live remaining distance + fastest-route ETA + per-signal GREEN-WAVE state,
  // recomputed every render (cheap) so they update smoothly as the unit moves.
  let distanceM: number | null = null
  let etaSec: number | null = null
  let signalsOut: RouteSignalState[] = signals.map((s) => ({ ...s, state: 'requested' as const, eta_sec: 0 }))
  if (active && gpsOk && lat != null && lng != null) {
    const mps = Math.max((state?.speed_kph ?? 0) / 3.6, MIN_ETA_MPS)
    if (path.length > 1) {
      const total = cumRef.current[cumRef.current.length - 1] ?? 0
      const ambAlong = distAlong(path, cumRef.current, { lat, lng })
      const remaining = Math.max(0, total - ambAlong)
      distanceM = Math.round(remaining)
      etaSec = Math.round(remaining / mps)
      // GREEN WAVE: signals just behind us = passed; within reach ahead =
      // granted (being cleared); further ahead = requested.
      signalsOut = signals.map((s) => {
        const ahead = s.distAlong - ambAlong
        const st: RouteSignalState['state'] =
          ahead < -PASS_MARGIN_M ? 'passed' : ahead <= GRANT_LOOKAHEAD_M ? 'granted' : 'requested'
        return { ...s, state: st, eta_sec: Math.max(0, Math.round(ahead / mps)) }
      })
    } else if (dest) {
      const rem = distance({ lat, lng }, { lat: dest.lat, lng: dest.lng })
      distanceM = Math.round(rem)
      etaSec = Math.round(rem / mps)
    }
  }

  return { path, signals: signalsOut, distanceM, etaSec, loading, note }
}
