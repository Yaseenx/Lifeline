import type { Hazard } from '../protocol'

export default function HazardBanner({
  hazards,
  onAck,
}: {
  hazards: Hazard[]
  onAck: (nodeId: string) => void
}) {
  if (!hazards.length) return null
  const h = hazards[0]
  return (
    <div className={`hazard-banner ${h.severity}`} onClick={() => onAck(h.node_id)}>
      <b>Hazard</b> {h.message || h.type}
      {h.lane ? ` · lane ${h.lane}` : ''}
      <span className="tap">tap to dismiss</span>
    </div>
  )
}
