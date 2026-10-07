import { useEffect } from 'react'
import { useAgentSocket } from './hooks/useAgentSocket'
import { useDeviceVehicle } from './hooks/useDeviceVehicle'
import MapView from './components/MapView'
import SosPanel from './components/SosPanel'
import StatusBar from './components/StatusBar'
import CorridorPanel from './components/CorridorPanel'
import HazardBanner from './components/HazardBanner'
import CodeBanner from './components/CodeBanner'
import TripTimer from './components/TripTimer'
import LiveBadge from './components/LiveBadge'
import DispatchPrompt from './components/DispatchPrompt'
import { useRouteToHospital } from './hooks/useRouteToHospital'

// Map is Google Maps (VITE_GOOGLE_MAPS_API_KEY) with an automatic Leaflet +
// OpenStreetMap fallback — see components/MapView.tsx.

// Data source. DEFAULT is the REAL, server-connected view — the phone's browser
// GPS is streamed to the on-device agent, which signs it and relays telemetry to
// the server, and the corridor shown is the server's (J1/J2/J3).
//   default        → agent over websocket (the real pipeline)
//   ?live=1        → standalone browser-GPS preview, NOT connected to the server
//                    (dev only; computes its own nearby signals for a solo test)
const params = new URLSearchParams(window.location.search)
const MODE: 'agent' | 'live' = params.has('live') ? 'live' : 'agent'

export default function App() {
  return <Dashboard />
}

function Dashboard() {
  const agent = useAgentSocket(MODE === 'agent')
  const live = useDeviceVehicle(MODE === 'live')
  const src = MODE === 'agent' ? agent : live
  const { state, linked, send } = src

  // The route to the hospital is computed IN THE BROWSER (reliable even when the
  // server can't reach the internet) and drawn directly; the server corridor
  // still supplies the controlled-junction (J1/J2/J3) states. Without a GPS fix
  // the position is unknown, so hide distance/ETA/countdowns until GPS is live.
  const route = useRouteToHospital(MODE === 'agent' ? state : null)
  const gpsOk = !!state?.gps_fix
  const corridorView = state?.corridor
    ? {
        ...state.corridor,
        // The SERVER computes the authoritative road-route ETA/distance; display it.
        // Fall back to the browser route only if the server hasn't provided one yet.
        dest_distance_m: gpsOk
          ? (state.corridor.dest_distance_m != null ? state.corridor.dest_distance_m : (MODE === 'agent' ? route.distanceM : null))
          : null,
        dest_eta_sec: gpsOk
          ? (state.corridor.dest_eta_sec != null ? state.corridor.dest_eta_sec : (MODE === 'agent' ? route.etaSec : null))
          : null,
        nodes: gpsOk ? state.corridor.nodes : state.corridor.nodes.map((n) => ({ ...n, eta_sec: null })),
      }
    : state?.corridor

  // REAL phone GPS: in agent mode, stream the browser's geolocation to the
  // on-device agent, which signs it and relays telemetry to the server.
  useEffect(() => {
    if (MODE !== 'agent' || typeof navigator === 'undefined' || !navigator.geolocation) return
    const id = navigator.geolocation.watchPosition(
      (pos) =>
        send('gps_fix', {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          speed_kph: (pos.coords.speed ?? 0) * 3.6,
          heading_deg: pos.coords.heading ?? 0,
        }),
      (err) => console.warn('[gps] geolocation error:', err.message),
      { enableHighAccuracy: true, maximumAge: 1000, timeout: 15000 },
    )
    return () => navigator.geolocation.clearWatch(id)
  }, [send])

  return (
    <div className="app">
      <MapView
        state={state}
        // Draw the SERVER corridor (road path + on-route signals coloured by state).
        // The browser route is passed only as a fallback when the server corridor is empty.
        routePath={MODE === 'agent' && !(state?.corridor?.path && state.corridor.path.length > 1) ? route.path : undefined}
        routeSignals={MODE === 'agent' && !(state?.corridor?.nodes && state.corridor.nodes.length) ? route.signals : undefined}
      />
      <StatusBar state={state} linked={linked} />
      <CodeBanner
        trip={state?.trip}
        etaSec={gpsOk ? (state?.corridor.dest_eta_sec ?? (MODE === 'agent' ? route.etaSec : null)) : null}
      />
      <HazardBanner hazards={state?.hazards ?? []} onAck={(id) => send('ack_hazard', { node_id: id })} />
      <CorridorPanel
        corridor={corridorView}
        destinationName={state?.trip.destination_name}
        routeSignalCount={gpsOk ? state?.corridor.nodes.length : undefined}
      />
      <TripTimer active={state?.trip.active ?? false} />
      <SosPanel state={state} send={send} />
      {MODE === 'agent' && <DispatchPrompt state={state} send={send} />}
      {MODE === 'live' && (
        <LiveBadge
          state={state}
          geoError={live.geoError}
          routeError={live.routeError}
          signalNote={live.signalNote}
        />
      )}
      {MODE === 'agent' && !linked && <div className="link-warn">Connecting to vehicle unit…</div>}
    </div>
  )
}
