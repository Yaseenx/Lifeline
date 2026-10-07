import type { CorridorState } from '../protocol'

const LABEL: Record<string, string> = {
  inactive: 'No corridor',
  planning: 'Planning corridor…',
  active: 'Corridor active',
  clearing: 'Clearing',
}

// Explicit grant semantics (MON-8 / SEC-10): only an explicit 'granted' (or a
// confirmed 'green') means the junction is cleared for this vehicle. Everything
// else — queued, requested, rejected, red, idle — means OBEY THE SIGNALS. The
// driver must never assume right-of-way from a missing or ambiguous state.
const GRANT: Record<string, { text: string; cls: 'granted' | 'wait' | 'rejected' }> = {
  granted: { text: 'GRANTED — junction cleared', cls: 'granted' },
  green: { text: 'GRANTED — junction cleared', cls: 'granted' },
  queued: { text: 'QUEUED — obey signals', cls: 'wait' },
  requested: { text: 'REQUESTED — obey signals', cls: 'wait' },
  idle: { text: 'NO GRANT — obey signals', cls: 'wait' },
  rejected: { text: 'REJECTED — obey signals', cls: 'rejected' },
  red: { text: 'STOP — signal is red', cls: 'rejected' },
}

const fmtDist = (m: number) => (m < 950 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`)
const fmtEta = (s: number | null | undefined) =>
  s == null ? '—' : s < 60 ? `${s}s` : `${Math.round(s / 60)} min`

export default function CorridorPanel({
  corridor,
  destinationName,
  routeSignalCount,
}: {
  corridor?: CorridorState
  destinationName?: string | null
  routeSignalCount?: number
}) {
  if (!corridor || corridor.status === 'inactive') {
    return <div className="corridor-panel idle">No active corridor</div>
  }
  // The next junction the vehicle has not yet passed drives the grant banner.
  const next = corridor.nodes.find((n) => n.state !== 'passed')
  const grant = next ? GRANT[next.state] ?? GRANT.idle : null
  return (
    <div className="corridor-panel">
      <div className="c-head">{LABEL[corridor.status] || corridor.status}</div>
      {grant && (
        <div className={`c-grant ${grant.cls}`}>
          {grant.text}
          {next?.name ? <span className="c-grant-node"> · {next.name}</span> : null}
        </div>
      )}
      {destinationName && (
        <div className="c-dest">
          → <b>{destinationName}</b>
        </div>
      )}
      {corridor.dest_distance_m != null && (
        <div className="c-metrics">
          <div className="c-metric">
            <span className="c-mlabel">Distance</span>
            <span className="c-mval">{fmtDist(corridor.dest_distance_m)}</span>
          </div>
          <div className="c-metric">
            <span className="c-mlabel">ETA</span>
            <span className="c-mval">{fmtEta(corridor.dest_eta_sec)}</span>
          </div>
        </div>
      )}
      {routeSignalCount != null && routeSignalCount > 0 && (
        <div className="c-signals-line" style={{ fontSize: 12, opacity: 0.75, marginTop: 6 }}>
          🚦 {routeSignalCount} on route · {corridor.nodes.filter((n) => n.controlled).length} controlled
        </div>
      )}
      {corridor.queue_position != null && (
        <div className="c-queue">
          Queue position: <b>{corridor.queue_position}</b>
        </div>
      )}
      {corridor.nodes.length > 0 && (
        <>
          <div className="c-sub">Upcoming signals 🚦</div>
          <ul className="c-nodes">
            {corridor.nodes.slice(0, 5).map((n) => (
              <li key={n.id}>
                <span className={`chip ${n.state}`} />
                <span className="c-name">
                  {n.name || n.id}
                  {n.green_in_s != null && n.green_in_s > 0 && (
                    <span className="c-green-in"> 🟢 in {Math.ceil(n.green_in_s)}s</span>
                  )}
                  {n.green_in_s === 0 && <span className="c-green-in now"> 🟢 green</span>}
                </span>
                <span className="c-eta">
                  {n.eta_sec != null ? `${Math.round(n.eta_sec)}s` : '—'}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
