import type { VehicleState } from '../protocol'

export default function StatusBar({ state, linked }: { state: VehicleState | null; linked: boolean }) {
  const speed = Math.round(state?.speed_kph ?? 0)
  const advisory = state?.corridor.safe_speed_kph
  const over = advisory != null && speed > advisory + 2

  return (
    <div className="status-bar">
      <span className={`dot ${linked ? 'ok' : 'bad'}`} />
      <span className="lbl">unit</span>
      <span className={`dot ${state?.cloud_connected ? 'ok' : 'bad'}`} />
      <span className="lbl">server</span>
      <span className={`dot ${state?.gps_fix ? 'ok' : 'bad'}`} />
      <span className="lbl">gps</span>
      <span className="speed">
        {speed}
        <small>km/h</small>
      </span>
      {advisory != null && (
        <span className={`advisory ${over ? 'over' : ''}`}>safe {Math.round(advisory)} km/h</span>
      )}
    </div>
  )
}
