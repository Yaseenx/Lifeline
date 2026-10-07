import type { VehicleState } from '../protocol'

// Live-GPS status chip (bottom-right). Shows whether we have a fix or an error.
export default function LiveBadge({
  state,
  geoError,
  routeError,
  signalNote,
}: {
  state: VehicleState | null
  geoError: string | null
  routeError?: string | null
  signalNote?: string | null
}) {
  const fix = state?.gps_fix ?? false
  return (
    <div className="live-badge">
      <div className="lb-head">
        <span className={`lb-dot ${fix ? 'ok' : ''}`} /> LIVE GPS
      </div>
      {geoError ? (
        <p className="lb-msg err">{geoError}</p>
      ) : fix ? (
        <p className="lb-msg">Tracking your real position. Move to see it update.</p>
      ) : (
        <p className="lb-msg">Waiting for a location fix… allow location access.</p>
      )}
      {routeError && <p className="lb-msg err">{routeError}</p>}
      {signalNote && <p className="lb-msg">🚦 {signalNote}</p>}
    </div>
  )
}
