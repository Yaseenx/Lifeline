import { useCallback, useEffect, useRef, useState } from 'react'
import type { CorridorNode, VehicleState } from '../protocol'
import { DEFAULT_HOSPITAL, HOSPITALS, hasEmergencyDept, nearestHospital, resolveHospital } from '../hospitals'
import { computeRoute } from '../route'
import { fetchSignalsAlongRoute, type RouteSignal } from '../signals'

const MAX_SIGNALS = 8 // how many upcoming signals to show

// Real-time vehicle source backed by the browser Geolocation API. The marker
// only moves when YOU move; speed is real (0 when stationary). Distance + ETA
// are computed from your live position along the planned road route.
// Used as the default in dev. Needs https or localhost + location permission.

type LatLng = { lat: number; lng: number }

const FALLBACK: LatLng = { lat: 13.0827, lng: 80.2707 } // shown until first GPS fix
const STOP_MPS = 0.7 // below this we treat the vehicle as stationary (GPS jitter)
// ETA floor speed: when stationary/crawling, estimate with the calibrated
// Chennai peak ambulance speed (~3 m/s = 11 km/h) instead of showing nothing.
const MIN_ETA_MPS = 3

// --- geo helpers (meters) ---
const R = 6371000
const toRad = (d: number) => (d * Math.PI) / 180
const toDeg = (r: number) => (r * 180) / Math.PI

function distance(a: LatLng, b: LatLng) {
  const dLat = toRad(b.lat - a.lat)
  const dLng = toRad(b.lng - a.lng)
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

function bearing(a: LatLng, b: LatLng) {
  const la = toRad(a.lat)
  const lb = toRad(b.lat)
  const dLng = toRad(b.lng - a.lng)
  const y = Math.sin(dLng) * Math.cos(lb)
  const x = Math.cos(la) * Math.sin(lb) - Math.sin(la) * Math.cos(lb) * Math.cos(dLng)
  return (toDeg(Math.atan2(y, x)) + 360) % 360
}

function cumulative(path: LatLng[]) {
  const cum = [0]
  for (let i = 1; i < path.length; i++) cum[i] = cum[i - 1] + distance(path[i - 1], path[i])
  return cum
}

// Closest point on segment a→b to p (planar approx, fine for short segments).
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

// How far along the route (m) the point projects to.
function distAlongRoute(path: LatLng[], cum: number[], p: LatLng) {
  let bestDist = Infinity
  let bestAlong = 0
  for (let i = 0; i < path.length - 1; i++) {
    const snap = projectOnSegment(p, path[i], path[i + 1])
    const d = distance(p, snap)
    if (d < bestDist) {
      bestDist = d
      bestAlong = cum[i] + distance(path[i], snap)
    }
  }
  return bestAlong
}

function initialState(): VehicleState {
  return {
    device_id: 'WEB-DEVICE',
    cloud_connected: true,
    gps_fix: false,
    lat: FALLBACK.lat,
    lng: FALLBACK.lng,
    speed_kph: 0,
    heading_deg: 0,
    ts: 0,
    trip: {
      active: false,
      trip_id: null,
      trip_type: 'SCENE',
      emergency: false,
      leg: 2,
      patient_onboard: false,
      origin_address: null,
      origin_lat: null,
      origin_lng: null,
      destination_id: null,
      destination_name: null,
      condition: null,
    },
    corridor: {
      status: 'inactive',
      queue_position: null,
      safe_speed_kph: null,
      nodes: [],
      path: null,
      dest_distance_m: null,
      dest_eta_sec: null,
    },
    hazards: [],
  }
}

export function useDeviceVehicle(enabled: boolean) {
  const [state, setState] = useState<VehicleState>(initialState)
  const [geoError, setGeoError] = useState<string | null>(null)
  const [routeError, setRouteError] = useState<string | null>(null)
  const [signalNote, setSignalNote] = useState<string | null>(null)

  const ref = useRef(state)
  ref.current = state

  // last fix for deriving speed/heading when the GPS doesn't report them
  const lastFix = useRef<{ lat: number; lng: number; t: number } | null>(null)
  // active route geometry + traffic signals along it
  const routePath = useRef<LatLng[]>([])
  const cumDist = useRef<number[]>([])
  const signals = useRef<RouteSignal[]>([])
  const tripCounter = useRef(0)
  // HARD RULE mirror: corridor/signal-request UI only for emergency trips.
  const emergencyRef = useRef(false)

  // Recompute live distance, ETA, and upcoming-signal nodes from the current
  // position and speed.
  const metricsFor = (pos: LatLng, speedKph: number) => {
    const t = ref.current.trip
    if (!t.active) return { dest_distance_m: null, dest_eta_sec: null, nodes: [] as CorridorNode[] }

    const mps = speedKph / 3.6
    const effMps = Math.max(mps, MIN_ETA_MPS) // never divide by ~zero
    let remaining: number
    let nodes: CorridorNode[] = []

    if (routePath.current.length > 1) {
      const total = cumDist.current[cumDist.current.length - 1]
      const along = distAlongRoute(routePath.current, cumDist.current, pos)
      remaining = Math.max(0, total - along)
      // upcoming signals: those still ahead of us on the route.
      // Non-emergency trips show no "requested" chips — nothing is requested.
      nodes = (emergencyRef.current ? signals.current : [])
        .filter((s) => s.distAlong >= along - 20)
        .slice(0, MAX_SIGNALS)
        .map((s, i) => ({
          id: `sig-${Math.round(s.distAlong)}`,
          name: `Signal ${i + 1}`,
          lat: s.lat,
          lng: s.lng,
          state: 'requested',
          eta_sec: Math.max(0, Math.round((s.distAlong - along) / effMps)),
        }))
    } else {
      const dest = resolveHospital(t.destination_id) ?? DEFAULT_HOSPITAL
      remaining = distance(pos, dest)
    }

    const eta = Math.round(remaining / effMps)
    return { dest_distance_m: Math.round(remaining), dest_eta_sec: eta, nodes }
  }

  // watch real position
  useEffect(() => {
    if (!enabled) return
    if (!('geolocation' in navigator)) {
      setGeoError('Geolocation not supported by this browser.')
      return
    }
    const id = navigator.geolocation.watchPosition(
      (p) => {
        setGeoError(null)
        const now = p.timestamp
        const pos = { lat: p.coords.latitude, lng: p.coords.longitude }

        // speed: trust the GPS when it reports it, else derive from movement
        let speedMps = Number.isFinite(p.coords.speed as number) ? (p.coords.speed as number) : NaN
        const prev = lastFix.current
        if (!Number.isFinite(speedMps) && prev) {
          const dt = (now - prev.t) / 1000
          if (dt > 0) speedMps = distance(prev, pos) / dt
        }
        if (!Number.isFinite(speedMps) || speedMps < STOP_MPS) speedMps = 0
        const speedKph = Math.round(speedMps * 3.6)

        // heading: GPS heading if moving, else bearing of travel, else keep last
        let heading = ref.current.heading_deg
        if (speedMps > STOP_MPS) {
          if (Number.isFinite(p.coords.heading as number)) heading = p.coords.heading as number
          else if (prev) heading = bearing(prev, pos)
        }

        lastFix.current = { ...pos, t: now }
        const m = metricsFor(pos, speedKph)

        setState((s) => ({
          ...s,
          gps_fix: true,
          lat: pos.lat,
          lng: pos.lng,
          speed_kph: speedKph,
          heading_deg: heading,
          ts: Math.round(now / 1000),
          corridor: { ...s.corridor, ...m },
        }))
      },
      (err) => {
        setGeoError(err.message || 'Location unavailable.')
        setState((s) => ({ ...s, gps_fix: false, speed_kph: 0 }))
      },
      { enableHighAccuracy: true, maximumAge: 1000, timeout: 15000 },
    )
    return () => navigator.geolocation.clearWatch(id)
  }, [enabled])

  const startRoute = useCallback((path: LatLng[]) => {
    routePath.current = path
    cumDist.current = cumulative(path)
    signals.current = []
    const here = { lat: ref.current.lat, lng: ref.current.lng }
    const m = metricsFor(here, ref.current.speed_kph)
    const emg = emergencyRef.current
    setState((p) => ({
      ...p,
      corridor: {
        status: emg ? 'active' : 'inactive',
        queue_position: emg ? 1 : null,
        safe_speed_kph: emg ? 38 : null,
        path,
        ...m,
      },
    }))
    // Fetch traffic signals along the route (free, async) and re-render nodes.
    if (emg) setSignalNote('Loading traffic signals…')
    fetchSignalsAlongRoute(path)
      .then((sigs) => {
        signals.current = sigs
        const pos = { lat: ref.current.lat, lng: ref.current.lng }
        const info = metricsFor(pos, ref.current.speed_kph)
        setState((p) => ({ ...p, corridor: { ...p.corridor, nodes: info.nodes } }))
        setSignalNote(sigs.length ? null : 'No mapped signals on this route.')
      })
      .catch((e: Error) => {
        console.warn('[live] signals failed:', e.message)
        setSignalNote('Traffic-signal service busy — try again.')
      })
  }, [])

  const send = useCallback(
    (action: string, payload: Record<string, unknown> = {}) => {
      const routeTo = (target: LatLng) => {
        const origin = { lat: ref.current.lat, lng: ref.current.lng }
        setRouteError(null)
        computeRoute(origin, target)
          .then((path) => startRoute(path))
          .catch((err: Error) => {
            console.warn('[live] route failed:', err.message)
            setRouteError(`Route unavailable: ${err.message}`)
            startRoute([origin, target]) // straight-line fallback
          })
      }

      const beginTrip = (
        tripType: 'SCENE' | 'HOUSE_CALL' | 'TRANSFER',
        emergency: boolean,
        p0: Record<string, unknown>,
      ) => {
        // Default destination = nearest suitable hospital from HERE (known-ED
        // pool for emergencies), not a fixed city-centre hospital.
        const here = ref.current
        const pool = emergency ? HOSPITALS.filter(hasEmergencyDept) : HOSPITALS
        const auto = nearestHospital(here.lat, here.lng, pool).hospital ?? DEFAULT_HOSPITAL
        const dest = resolveHospital(ref.current.trip.destination_id) ?? auto
        const oLat = typeof p0.origin_lat === 'number' ? p0.origin_lat : null
        const oLng = typeof p0.origin_lng === 'number' ? p0.origin_lng : null
        const leg: 1 | 2 = tripType === 'HOUSE_CALL' ? 1 : 2
        tripCounter.current += 1
        emergencyRef.current = emergency
        setState((p) => ({
          ...p,
          trip: {
            ...p.trip,
            active: true,
            trip_id: `TRIP-${tripCounter.current}`,
            trip_type: tripType,
            emergency,
            leg,
            patient_onboard: false,
            origin_address: (p0.origin_address as string | null) ?? null,
            origin_lat: oLat,
            origin_lng: oLng,
            destination_id: p.trip.destination_id ?? dest.id,
            destination_name: p.trip.destination_name ?? dest.name,
          },
          corridor: {
            status: emergency ? 'planning' : 'inactive',
            queue_position: emergency ? 1 : null,
            safe_speed_kph: emergency ? 38 : null,
            nodes: [],
            path: null,
            dest_distance_m: null,
            dest_eta_sec: null,
          },
        }))
        // Leg 1 routes to the pickup point only when dispatch gave coordinates;
        // with an address alone we draw no route (a line to the hospital while
        // heading to a house is misleading). Leg 2 routes to the hospital.
        if (leg === 1) {
          if (oLat != null && oLng != null) routeTo({ lat: oLat, lng: oLng })
        } else {
          routeTo({ lat: dest.lat, lng: dest.lng })
        }
      }

      const endTrip = () => {
        routePath.current = []
        cumDist.current = []
        signals.current = []
        emergencyRef.current = false
        setRouteError(null)
        setSignalNote(null)
        setState((p) => ({
          ...initialState(),
          gps_fix: p.gps_fix,
          lat: p.lat,
          lng: p.lng,
          speed_kph: p.speed_kph,
          heading_deg: p.heading_deg,
          ts: p.ts,
        }))
      }

      if (action === 'sos') {
        if (payload.active) beginTrip('SCENE', true, payload)
        else endTrip()
      } else if (action === 'start_trip') {
        const tt = (payload.trip_type as 'SCENE' | 'HOUSE_CALL' | 'TRANSFER') ?? 'SCENE'
        beginTrip(tt, !!payload.emergency, payload)
      } else if (action === 'end_trip') {
        endTrip()
      } else if (action === 'patient_onboard') {
        const t = ref.current.trip
        if (t.active && t.leg === 1) {
          const dest = resolveHospital(t.destination_id) ?? DEFAULT_HOSPITAL
          setState((p) => ({ ...p, trip: { ...p.trip, leg: 2, patient_onboard: true } }))
          routeTo({ lat: dest.lat, lng: dest.lng })
        }
      } else if (action === 'escalate') {
        if (ref.current.trip.active && !ref.current.trip.emergency) {
          emergencyRef.current = true
          setState((p) => ({
            ...p,
            trip: { ...p.trip, emergency: true, condition: (payload.condition as string | null) ?? p.trip.condition },
            corridor: { ...p.corridor, status: 'active', queue_position: 1, safe_speed_kph: 38 },
          }))
        }
      } else if (action === 'deescalate') {
        if (ref.current.trip.active && ref.current.trip.emergency) {
          emergencyRef.current = false
          setState((p) => ({
            ...p,
            trip: { ...p.trip, emergency: false },
            corridor: { ...p.corridor, status: 'inactive', queue_position: null, safe_speed_kph: null, nodes: [] },
          }))
        }
      } else if (action === 'set_trip') {
        const t = ref.current.trip
        const newDest = (payload.destination_id as string | null) ?? null
        const destChanged = t.active && !!newDest && newDest !== t.destination_id
        setState((p) => ({
          ...p,
          trip: {
            ...p.trip,
            destination_id: newDest,
            destination_name: (payload.destination_name as string | null) ?? null,
            condition: (payload.condition as string | null) ?? null,
          },
        }))
        // Destination changed mid-trip: recompute the route so the line on the
        // map (and distance/ETA) actually lead to the newly chosen hospital.
        if (destChanged && t.leg === 2) {
          const h = resolveHospital(newDest)
          if (h) routeTo({ lat: h.lat, lng: h.lng })
        }
      } else if (action === 'ack_hazard') {
        setState((p) => ({
          ...p,
          hazards: p.hazards.filter((h) => h.node_id !== payload.node_id),
        }))
      }
    },
    [startRoute],
  )

  return { state, linked: true, send, geoError, routeError, signalNote }
}
