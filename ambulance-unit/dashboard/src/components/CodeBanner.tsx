import type { TripState } from '../protocol'

// Top banner: patient code + ETA for emergencies; teal banner for
// non-emergency trips (which never get a corridor); leg chip for house calls.

const fmtEta = (s: number | null | undefined) =>
  s == null ? '—' : s < 60 ? `${s}s` : `${Math.round(s / 60)} min`

export default function CodeBanner({
  trip,
  etaSec,
}: {
  trip: TripState | null | undefined
  etaSec: number | null | undefined
}) {
  if (!trip?.active) return null

  const legChip =
    trip.trip_type === 'HOUSE_CALL' ? (
      <span className="cb-leg">{trip.leg === 1 ? 'LEG 1 · TO PICKUP' : 'LEG 2 · TO HOSPITAL'}</span>
    ) : null

  if (!trip.emergency) {
    const label = trip.trip_type === 'HOUSE_CALL' ? 'HOUSE CALL · Non-emergency' : 'TRANSPORT · Non-emergency'
    return (
      <div className="code-banner routine">
        <span className="cb-code">{label}</span>
        {legChip}
        <span className="cb-eta">
          ETA <b>{fmtEta(etaSec)}</b>
        </span>
      </div>
    )
  }

  if (!trip.condition) {
    return (
      <div className="code-banner pending">
        <span className="cb-code">EMERGENCY · set patient condition</span>
        {legChip}
        <span className="cb-eta">
          ETA <b>{fmtEta(etaSec)}</b>
        </span>
      </div>
    )
  }

  const isRed = trip.condition === 'code_red'
  const label = isRed ? 'CODE RED · Life Threatening' : 'CODE BLUE · Non-Life Threatening'
  return (
    <div className={`code-banner ${isRed ? 'red' : 'blue'}`}>
      <span className="cb-code">{label}</span>
      {legChip}
      <span className="cb-eta">
        ETA <b>{fmtEta(etaSec)}</b>
      </span>
    </div>
  )
}
