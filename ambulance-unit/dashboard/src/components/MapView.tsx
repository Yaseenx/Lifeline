import { useEffect, useRef, useState } from 'react'
import {
  APIProvider,
  Map as GMap,
  useMap,
  useApiLoadingStatus,
  APILoadingStatus,
} from '@vis.gl/react-google-maps'
import type { VehicleState } from '../protocol'
import { resolveHospital } from '../hospitals'

// Map strategy: Google Maps is PRIMARY (needs VITE_GOOGLE_MAPS_API_KEY).
// If the key is missing, rejected, or the API fails to load, the view falls
// back automatically to Leaflet + OpenStreetMap (keyless) so the map can never
// white-screen during a demo. Leaflet is loaded from a <script> in index.html.
//
// Overlays (both renderers):
//   • routePath      — the fastest road route to the chosen hospital (blue line)
//   • routeSignals   — EVERY traffic signal along that route (amber context dots)
//   • corridor.nodes — the LifeLine-CONTROLLED junctions, drawn on top and
//                      coloured by live state (these are the ones that go green)
declare const L: any

type LL = { lat: number; lng: number }

const GOOGLE_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined
const KEY_OK = !!GOOGLE_KEY && GOOGLE_KEY !== 'your-google-maps-api-key'

const CENTER = { lat: 13.0827, lng: 80.2707 } // Chennai pilot corridor
const SIGNAL_COLOR = '#e8a33d' // uncontrolled signal (context)
const NEAR_NODE_M = 60 // hide a context signal this close to a controlled junction

const NODE_COLORS: Record<string, string> = {
  granted: '#1faa59',
  green: '#1faa59',
  red: '#e23b3b',
  requested: '#e8a33d',
  queued: '#e8a33d',
  rejected: '#5a6b7d',
  passed: '#5a6b7d',
  idle: '#8aa0b6',
}

const DARK_STYLE: any[] = [
  { elementType: 'geometry', stylers: [{ color: '#1b212b' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#8b98a5' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#0e1116' }] },
  { featureType: 'administrative', elementType: 'geometry', stylers: [{ color: '#3a4553' }] },
  { featureType: 'administrative.locality', elementType: 'labels.text.fill', stylers: [{ color: '#c8d2dd' }] },
  { featureType: 'poi', elementType: 'labels.text.fill', stylers: [{ color: '#8b98a5' }] },
  { featureType: 'poi.park', elementType: 'geometry', stylers: [{ color: '#16241a' }] },
  { featureType: 'road', elementType: 'geometry.fill', stylers: [{ color: '#2b3543' }] },
  { featureType: 'road', elementType: 'labels.text.fill', stylers: [{ color: '#9aa7b4' }] },
  { featureType: 'road.arterial', elementType: 'geometry', stylers: [{ color: '#39485a' }] },
  { featureType: 'road.highway', elementType: 'geometry', stylers: [{ color: '#46586d' }] },
  { featureType: 'transit', elementType: 'labels.text.fill', stylers: [{ color: '#8b98a5' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#0b1622' }] },
  { featureType: 'water', elementType: 'labels.text.fill', stylers: [{ color: '#3d5773' }] },
]

const Re = 6371000
const toRad = (d: number) => (d * Math.PI) / 180
function metersBetween(a: LL, b: LL) {
  const dLat = toRad(b.lat - a.lat)
  const dLng = toRad(b.lng - a.lng)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2
  return 2 * Re * Math.asin(Math.sqrt(h))
}

type SignalPt = LL & { state?: string }

// Green-wave style for an on-route signal by its state.
function sigStyle(st?: string) {
  const granted = st === 'granted'
  return {
    color: NODE_COLORS[st || ''] || SIGNAL_COLOR,
    scale: granted ? 6 : 4,
    tip: granted ? 'Signal — clearing (green wave)' : st === 'passed' ? 'Signal — passed' : 'Signal on route',
  }
}

// Context signals with any coinciding controlled junction removed (the coloured
// controlled node is drawn there instead).
function contextSignals(routeSignals: SignalPt[] | undefined, nodes: LL[]): SignalPt[] {
  if (!routeSignals?.length) return []
  return routeSignals.filter((s) => !nodes.some((n) => metersBetween(n, s) < NEAR_NODE_M))
}

interface MapProps {
  state: VehicleState | null
  routePath?: LL[]
  routeSignals?: SignalPt[]
}

// ===========================================================================
// Dispatcher: Google when the key is usable, else Leaflet. Falls back on the
// Google API reporting an auth/load failure.
// ===========================================================================
export default function MapView({ state, routePath, routeSignals }: MapProps) {
  const [fellBack, setFellBack] = useState(false)

  if (KEY_OK && !fellBack) {
    return (
      <APIProvider apiKey={GOOGLE_KEY as string}>
        <GoogleLayer state={state} routePath={routePath} routeSignals={routeSignals} onFail={() => setFellBack(true)} />
      </APIProvider>
    )
  }
  return <LeafletLayer state={state} routePath={routePath} routeSignals={routeSignals} />
}

// ---------------------------------------------------------------------------
// Google Maps layer
// ---------------------------------------------------------------------------
function GoogleLayer({ state, routePath, routeSignals, onFail }: MapProps & { onFail: () => void }) {
  const status = useApiLoadingStatus()
  const failed = status === APILoadingStatus.AUTH_FAILURE || status === APILoadingStatus.FAILED

  useEffect(() => {
    if (failed) {
      console.warn('[map] Google Maps unavailable (', status, ') — switching to OpenStreetMap')
      onFail()
    }
  }, [failed, status, onFail])

  if (failed) return <LeafletLayer state={state} routePath={routePath} routeSignals={routeSignals} />

  return (
    <GMap
      className="map"
      style={{ width: '100%', height: '100%' }}
      defaultCenter={{ lat: state?.lat || CENTER.lat, lng: state?.lng || CENTER.lng }}
      defaultZoom={15}
      gestureHandling="greedy"
      disableDefaultUI={true}
      clickableIcons={false}
      styles={DARK_STYLE}
    >
      <GoogleOverlays state={state} routePath={routePath} routeSignals={routeSignals} />
    </GMap>
  )
}

function GoogleOverlays({ state, routePath, routeSignals }: MapProps) {
  const map = useMap()
  const g = useRef<any>({ nodes: {}, sigs: {}, sigKey: null, amb: null, dest: null, line: null })
  const centered = useRef(false)

  useEffect(() => {
    const gm = (window as any).google
    if (!map || !gm?.maps) return
    const lat = state?.lat || CENTER.lat
    const lng = state?.lng || CENTER.lng
    const corridor = state?.corridor
    // when the browser supplies the green wave (routeSignals), only draw the
    // server's CONTROLLED junctions here, so route signals aren't drawn twice
    const nodes = (routeSignals && routeSignals.length)
      ? (corridor?.nodes ?? []).filter((n) => !!n.controlled && n.state !== 'idle' && n.state !== 'passed')
      : (corridor?.nodes ?? [])
    const line =
      routePath && routePath.length > 1
        ? routePath
        : corridor?.path && corridor.path.length > 1
          ? corridor.path
          : nodes.map((n) => ({ lat: n.lat, lng: n.lng }))
    const tr = state?.trip
    const destH = tr?.active ? resolveHospital(tr.destination_id) : undefined
    // leg 1 = drive to the ACCIDENT / pickup (origin); leg 2 = to the hospital
    const dest = !tr?.active
      ? undefined
      : tr.leg === 1 && tr.origin_lat != null && tr.origin_lng != null
        ? { lat: tr.origin_lat, lng: tr.origin_lng, name: tr.origin_address || 'Accident scene', scene: true }
        : destH
          ? { lat: destH.lat, lng: destH.lng, name: destH.name, scene: false }
          : undefined
    const R = g.current

    // route polyline
    if (R.line) { R.line.setMap(null); R.line = null }
    if (line.length > 1) {
      R.line = new gm.maps.Polyline({
        path: line.map((p: any) => ({ lat: p.lat, lng: p.lng })),
        strokeColor: '#2e6cff', strokeOpacity: 0.9, strokeWeight: 6, map,
      })
    }

    // ALL traffic signals along the route (context) — rebuilt only when the set
    // changes, drawn UNDER the controlled junctions.
    const activeSigs = new Set<string>()
    contextSignals(routeSignals, nodes).forEach((s) => {
      const id = `${s.lat},${s.lng}`
      activeSigs.add(id)
      const ss = sigStyle(s.state)
      let m = R.sigs[id]
      if (!m) {
        m = new gm.maps.Marker({ map, zIndex: s.state === 'granted' ? 400 : 300 })
        R.sigs[id] = m
      }
      m.setPosition({ lat: s.lat, lng: s.lng })
      m.setTitle(ss.tip)
      m.setIcon({ path: gm.maps.SymbolPath.CIRCLE, scale: ss.scale, fillColor: ss.color,
                  fillOpacity: 0.95, strokeColor: '#0e1116', strokeWeight: 1 })
      m.setZIndex(s.state === 'granted' ? 400 : 300)
    })
    Object.keys(R.sigs).forEach((id) => {
      if (!activeSigs.has(id)) { R.sigs[id].setMap(null); delete R.sigs[id] }
    })

    // corridor signal nodes (LifeLine-controlled) on top
    const seen = new Set<string>()
    nodes.forEach((n) => {
      seen.add(n.id)
      const color = NODE_COLORS[n.state] || NODE_COLORS.idle
      const ctrl = !!n.controlled  // controller site vs a live route signal
      let m = R.nodes[n.id]
      if (!m) {
        m = new gm.maps.Marker({ map, title: ctrl ? `${n.name} (controlled)` : n.name, zIndex: ctrl ? 620 : 500 })
        R.nodes[n.id] = m
      }
      m.setPosition({ lat: n.lat, lng: n.lng })
      m.setIcon({ path: gm.maps.SymbolPath.CIRCLE, scale: ctrl ? 9 : 6, fillColor: color,
                  fillOpacity: 1, strokeColor: ctrl ? '#fff' : '#0e1116', strokeWeight: ctrl ? 3 : 1 })
    })
    Object.keys(R.nodes).forEach((id) => {
      if (!seen.has(id)) { R.nodes[id].setMap(null); delete R.nodes[id] }
    })

    // destination hospital
    if (R.dest) { R.dest.setMap(null); R.dest = null }
    if (dest) {
      R.dest = new gm.maps.Marker({
        map, position: { lat: dest.lat, lng: dest.lng },
        title: dest.scene ? `Accident · ${dest.name}` : dest.name,
        label: { text: dest.scene ? 'A' : 'H', color: '#fff', fontWeight: '700', fontSize: '13px' },
        icon: { path: gm.maps.SymbolPath.CIRCLE, scale: 13, fillColor: dest.scene ? '#f5a623' : '#e23b3b',
                fillOpacity: 1, strokeColor: '#fff', strokeWeight: 2 },
        zIndex: 900,
      })
    }

    // ambulance
    if (state?.gps_fix) {
      if (!R.amb) {
        R.amb = new gm.maps.Marker({ map, title: state.device_id || 'ambulance', zIndex: 999 })
      }
      R.amb.setPosition({ lat, lng })
      R.amb.setIcon({ path: gm.maps.SymbolPath.CIRCLE, scale: 8, fillColor: '#2e6cff',
                      fillOpacity: 1, strokeColor: '#fff', strokeWeight: 3 })
      if (!centered.current) { map.setCenter({ lat, lng }); map.setZoom(15); centered.current = true }
      else map.panTo({ lat, lng })
    }
  }, [map, state, routePath, routeSignals])

  return null
}

// ---------------------------------------------------------------------------
// Leaflet + OpenStreetMap fallback (keyless)
// ---------------------------------------------------------------------------
function LeafletLayer({ state, routePath, routeSignals }: MapProps) {
  const elRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<any>(null)
  const layers = useRef<any>({ nodes: {}, sigs: {}, sigKey: null, amb: null, dest: null, line: null })
  const centered = useRef(false)

  useEffect(() => {
    if (mapRef.current || !elRef.current || typeof L === 'undefined') return
    const map = L.map(elRef.current, { zoomControl: true })
      .setView([state?.lat || CENTER.lat, state?.lng || CENTER.lng], 15)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap', maxZoom: 19,
    }).addTo(map)
    mapRef.current = map
    setTimeout(() => map.invalidateSize(), 200)
    return () => { map.remove(); mapRef.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || typeof L === 'undefined') return
    const lat = state?.lat || CENTER.lat
    const lng = state?.lng || CENTER.lng
    const corridor = state?.corridor
    // when the browser supplies the green wave (routeSignals), only draw the
    // server's CONTROLLED junctions here, so route signals aren't drawn twice
    const nodes = (routeSignals && routeSignals.length)
      ? (corridor?.nodes ?? []).filter((n) => !!n.controlled && n.state !== 'idle' && n.state !== 'passed')
      : (corridor?.nodes ?? [])
    const line =
      routePath && routePath.length > 1
        ? routePath
        : corridor?.path && corridor.path.length > 1
          ? corridor.path
          : nodes.map((n) => ({ lat: n.lat, lng: n.lng }))
    const tr = state?.trip
    const destH = tr?.active ? resolveHospital(tr.destination_id) : undefined
    // leg 1 = drive to the ACCIDENT / pickup (origin); leg 2 = to the hospital
    const dest = !tr?.active
      ? undefined
      : tr.leg === 1 && tr.origin_lat != null && tr.origin_lng != null
        ? { lat: tr.origin_lat, lng: tr.origin_lng, name: tr.origin_address || 'Accident scene', scene: true }
        : destH
          ? { lat: destH.lat, lng: destH.lng, name: destH.name, scene: false }
          : undefined
    const g = layers.current

    // route polyline
    if (g.line) { map.removeLayer(g.line); g.line = null }
    if (line.length > 1) {
      g.line = L.polyline(line.map((p: any) => [p.lat, p.lng]),
        { color: '#2e6cff', weight: 6, opacity: 0.85 }).addTo(map)
    }

    // ALL traffic signals along the route (context), rebuilt only when changed
    const activeSigs = new Set<string>()
    contextSignals(routeSignals, nodes).forEach((s) => {
      const id = `${s.lat},${s.lng}`
      activeSigs.add(id)
      const ss = sigStyle(s.state)
      let m = g.sigs[id]
      if (!m) {
        m = L.circleMarker([s.lat, s.lng], { weight: 1, color: '#0e1116', fillOpacity: 0.95 })
             .addTo(map).bindTooltip(ss.tip, { direction: 'top' })
        g.sigs[id] = m
      }
      m.setLatLng([s.lat, s.lng]).setRadius(ss.scale).setStyle({ fillColor: ss.color })
      m.setTooltipContent(ss.tip)
    })
    Object.keys(g.sigs).forEach((id) => {
      if (!activeSigs.has(id)) { map.removeLayer(g.sigs[id]); delete g.sigs[id] }
    })

    // corridor signal nodes (controlled) on top
    const seen = new Set<string>()
    nodes.forEach((n) => {
      seen.add(n.id)
      const color = NODE_COLORS[n.state] || NODE_COLORS.idle
      const ctrl = !!n.controlled  // controller site vs a live route signal
      let m = g.nodes[n.id]
      if (!m) {
        m = L.circleMarker([n.lat, n.lng], { radius: ctrl ? 9 : 6, weight: ctrl ? 3 : 1 })
          .addTo(map).bindTooltip(ctrl ? `${n.name} (controlled)` : n.name, { direction: 'top' })
        g.nodes[n.id] = m
      }
      m.setLatLng([n.lat, n.lng]).setRadius(ctrl ? 9 : 6)
        .setStyle({ color: ctrl ? '#fff' : '#0e1116', fillColor: color, fillOpacity: 0.9, weight: ctrl ? 3 : 1 })
    })
    Object.keys(g.nodes).forEach((id) => {
      if (!seen.has(id)) { map.removeLayer(g.nodes[id]); delete g.nodes[id] }
    })

    // destination hospital
    if (g.dest) { map.removeLayer(g.dest); g.dest = null }
    if (dest) {
      const dc = dest.scene ? '#f5a623' : '#e23b3b'
      const dl = dest.scene ? 'A' : 'H'
      g.dest = L.marker([dest.lat, dest.lng], {
        icon: L.divIcon({
          className: '', iconSize: [26, 26],
          html: `<div style="width:26px;height:26px;border-radius:50%;background:${dc};color:#fff;font:700 14px system-ui;display:flex;align-items:center;justify-content:center;border:2px solid #fff">${dl}</div>`,
        }),
      }).addTo(map).bindTooltip(dest.scene ? `Accident · ${dest.name}` : dest.name, { direction: 'top' })
    }

    // ambulance
    if (state?.gps_fix) {
      if (!g.amb) {
        g.amb = L.circleMarker([lat, lng], {
          radius: 8, weight: 3, color: '#fff', fillColor: '#2e6cff', fillOpacity: 0.95,
        }).addTo(map).bindTooltip(state.device_id || 'ambulance', { direction: 'right', offset: [8, 0] })
      }
      g.amb.setLatLng([lat, lng])
      if (!centered.current) { map.setView([lat, lng], 15); centered.current = true }
      else map.panTo([lat, lng], { animate: true })
    }
  }, [state, routePath, routeSignals])

  return <div ref={elRef} className="map" style={{ width: '100%', height: '100%' }} />
}
