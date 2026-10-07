import { useState } from 'react'
import type { TripType, VehicleState } from '../protocol'
import { hasEmergencyDept, isGeneralEmergencyDept, type Hospital } from '../hospitals'
import { useNearbyHospitals } from '../hooks/useNearbyHospitals'
import { useHospitalBeds } from '../hooks/useHospitalBeds'

const MAX_NEARBY = 25 // cap the live section so the picker stays scannable

type Send = (action: string, payload?: Record<string, unknown>) => void

const fmtKm = (km?: number) => (km == null ? '' : ` · ${km.toFixed(1)} km`)

export default function SosPanel({ state, send }: { state: VehicleState | null; send: Send }) {
  const trip = state?.trip
  const active = trip?.active ?? false
  const [dest, setDest] = useState('')
  const [cond, setCond] = useState('')
  // house-call setup fields
  const [pickupMode, setPickupMode] = useState<TripType | null>(null)
  const [originAddr, setOriginAddr] = useState('')
  const [originLatLng, setOriginLatLng] = useState('') // optional "lat,lng" from dispatch
  const [houseEmergency, setHouseEmergency] = useState(false)

  // Verified list + every mapped hospital near the live GPS, nearest first.
  const gpsOk = !!state?.gps_fix && !!state.lat && !!state.lng
  const { hospitals, loading, note } = useNearbyHospitals(state?.lat, state?.lng, gpsOk)

  const verified = hospitals.filter((h) => h.verified)
  const nearby = hospitals.filter((h) => !h.verified).slice(0, MAX_NEARBY)
  // Google-Maps-style nearest, but emergency-aware: an emergency trip is
  // suggested the nearest hospital with a KNOWN emergency department, even if
  // closer no-known-ED hospitals get skipped. Non-emergency = nearest overall.
  // Live verified-hospital bed availability (from the hospital consoles).
  const beds = useHospitalBeds()
  const bedOf = (id?: string | null) => (id ? beds[id] : undefined)
  const openWithFree = (h: Hospital) => {
    const b = beds[h.id]
    return !!b && b.ed_open !== false && (b.beds_available ?? 0) > 0
  }
  // Short label for a hospital's beds — only when a hospital has actually reported.
  const bedShort = (id?: string | null): string => {
    const b = bedOf(id)
    if (!b || !b.updated) return ''
    if (b.ed_open === false) return ' · ED closed'
    const n = b.beds_available
    return ' · ED open' + (n != null ? ` · ${n} bed${n === 1 ? '' : 's'}` : '')
  }

  const nearestOverall = gpsOk && hospitals[0]?.distKm != null ? hospitals[0] : null
  const nearestEd = gpsOk ? hospitals.find((h) => h.distKm != null && isGeneralEmergencyDept(h)) ?? null : null
  // Prefer the nearest ED that is OPEN with beds free — but this is only a
  // suggestion; the crew still chooses. Falls back to the nearest ED.
  const nearestEdCap = gpsOk
    ? hospitals.find((h) => h.distKm != null && isGeneralEmergencyDept(h) && openWithFree(h)) ?? null
    : null
  const isEmergency = trip?.emergency ?? false
  const nearest = isEmergency ? nearestEdCap ?? nearestEd : nearestOverall
  const suggestLabel = isEmergency ? (nearestEdCap ? 'Nearest ED with beds:' : 'Nearest ED:') : 'Nearest:'
  const skipped =
    isEmergency && nearest && nearestOverall && nearest.id !== nearestOverall.id ? nearestOverall : null

  const pushTrip = (d: string, c: string) => {
    const h = hospitals.find((x) => x.id === d)
    send('set_trip', {
      destination_id: d || null,
      destination_name: h?.name || null,
      // coordinates ride along so the server (and ops map) know exactly
      // where this vehicle is headed, even for live map-data hospitals
      destination_lat: h?.lat ?? null,
      destination_lng: h?.lng ?? null,
      condition: c || null,
    })
  }

  const chooseDest = (d: string) => {
    setDest(d)
    pushTrip(d, cond)
  }

  const parseLatLng = (s: string): { lat: number; lng: number } | null => {
    const m = s.split(',').map((x) => parseFloat(x.trim()))
    return m.length === 2 && m.every(Number.isFinite) ? { lat: m[0], lng: m[1] } : null
  }

  const startTrip = (tripType: TripType, emergency: boolean) => {
    const ll = tripType === 'HOUSE_CALL' ? parseLatLng(originLatLng) : null
    send('start_trip', {
      trip_type: tripType,
      emergency,
      origin_address: tripType === 'HOUSE_CALL' ? originAddr || null : null,
      origin_lat: ll?.lat ?? null,
      origin_lng: ll?.lng ?? null,
    })
    setPickupMode(null)
  }

  // ---------- ACTIVE TRIP ----------
  if (active && trip) {
    const typeLabel =
      trip.trip_type === 'HOUSE_CALL' ? 'House call' : trip.trip_type === 'TRANSFER' ? 'Transfer' : 'Emergency'
    return (
      <div className="sos-panel">
        <div className={`trip-head ${trip.emergency ? 'emergency' : 'routine'}`}>
          <span>
            {typeLabel}
            {trip.emergency ? ' · EMERGENCY' : ' · non-emergency'}
          </span>
          {(trip.trip_type === 'HOUSE_CALL' || trip.origin_lat != null) && (
            <span className="trip-leg">
              leg {trip.leg} —{' '}
              {trip.leg === 1 ? (trip.trip_type === 'HOUSE_CALL' ? 'to pickup' : 'to accident') : 'to hospital'}
            </span>
          )}
        </div>

        {trip.leg === 1 && trip.origin_lat != null && (
          <>
            {trip.origin_address && (
              <div className="trip-origin">
                {trip.trip_type === 'HOUSE_CALL' ? 'Pickup' : 'Accident'}: {trip.origin_address}
              </div>
            )}
            <button className="onboard-btn" onClick={() => send('patient_onboard')}>
              {trip.trip_type === 'HOUSE_CALL'
                ? 'Patient onboard → go to hospital'
                : 'Arrived at scene · patient onboard → hospital'}
            </button>
          </>
        )}

        <label className="field">
          Destination
          {nearest && (
            <button type="button" className="nearest-pop" onClick={() => chooseDest(nearest.id)}>
              <span className="np-pin">📍</span>
              <span className="np-text">
                {suggestLabel} <b>{nearest.name}</b>
                {fmtKm(nearest.distKm)}{bedShort(nearest.id)}
              </span>
              <span className={`np-tag ${nearest.verified ? 'verified' : ''}`}>
                {nearest.verified ? '✓ verified ED' : nearest.emergency === 'yes' ? 'ED · map data' : 'map data'}
              </span>
              <span className="np-use">Use</span>
            </button>
          )}
          {skipped && (
            <span className="live-note">
              Skipped {skipped.name}{fmtKm(skipped.distKm)} —{' '}
              {skipped.specialty ? `${skipped.specialty} specialty only` : 'no known emergency dept.'}
            </span>
          )}
          <select value={trip.destination_id ?? dest} onChange={(e) => chooseDest(e.target.value)}>
            <option value="">Select hospital…</option>
            <optgroup label="Verified emergency hospitals">
              {verified.map((h) => (
                <option key={h.id} value={h.id}>
                  ✓ {h.name}{fmtKm(h.distKm)}{bedShort(h.id)}
                </option>
              ))}
            </optgroup>
            <optgroup label={`Nearby hospitals — live map data${loading ? ' (updating…)' : ''}`}>
              {nearby.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name}{fmtKm(h.distKm)}{h.emergency === 'yes' ? ' · ED' : ' · ED unknown'}{bedShort(h.id)}
                </option>
              ))}
            </optgroup>
          </select>
          {(() => {
            const b = bedOf(trip.destination_id ?? dest)
            if (!b || !b.updated) return null
            const closed = b.ed_open === false
            return (
              <span className={`dest-beds ${closed ? 'closed' : 'open'}`}>
                {closed
                  ? 'Selected hospital · ED closed / on diversion'
                  : `Selected hospital · ED open${b.beds_available != null ? ` · ${b.beds_available} beds free` : ''}${b.icu_available != null ? ` · ICU ${b.icu_available}` : ''}`}
              </span>
            )
          })()}
          {note && <span className="live-note">{note}</span>}
        </label>

        {trip.emergency && (
          <div className="field">
            Patient condition
            <div className="cond-btns">
              <button
                type="button"
                className={`cond-btn red ${(trip.condition ?? cond) === 'code_red' ? 'active' : ''}`}
                onClick={() => {
                  setCond('code_red')
                  pushTrip(trip.destination_id ?? dest, 'code_red')
                }}
              >
                🔴 Red SOS — Life threatening
              </button>
              <button
                type="button"
                className={`cond-btn blue ${(trip.condition ?? cond) === 'code_blue' ? 'active' : ''}`}
                onClick={() => {
                  setCond('code_blue')
                  pushTrip(trip.destination_id ?? dest, 'code_blue')
                }}
              >
                🔵 Blue SOS — Seriously injured, not life threatening
              </button>
              <button
                type="button"
                className="cond-btn escalate"
                disabled={(trip.condition ?? cond) !== 'code_blue'}
                onClick={() => {
                  setCond('code_red')
                  pushTrip(trip.destination_id ?? dest, 'code_red')
                }}
              >
                ⬆ Escalate — Blue → Red
              </button>
            </div>
          </div>
        )}

        {trip.emergency && !trip.condition && (
          <div className="hint">No condition set — the unit applies the default shortly.</div>
        )}

        <div className="trip-actions">
          {!trip.emergency ? (
            <button
              className="escalate-btn"
              onClick={() => send('escalate', cond ? { condition: cond } : {})}
            >
              ⚠ Escalate to emergency
            </button>
          ) : (
            <button className="deescalate-btn" onClick={() => send('deescalate')}>
              De-escalate — release corridor
            </button>
          )}
          <button className="end-btn" onClick={() => send('end_trip')}>
            End trip
          </button>
        </div>
      </div>
    )
  }

  // ---------- HOUSE-CALL / TRANSFER SETUP ----------
  if (pickupMode) {
    const isHouse = pickupMode === 'HOUSE_CALL'
    return (
      <div className="sos-panel">
        <div className="trip-head routine">{isHouse ? 'House call — setup' : 'Transfer — setup'}</div>
        {isHouse && (
          <>
            <label className="field">
              Pickup address
              <input
                type="text"
                value={originAddr}
                placeholder="12, Anna St, Kilpauk"
                onChange={(e) => setOriginAddr(e.target.value)}
              />
            </label>
            <label className="field">
              Pickup lat,lng (optional — from dispatch)
              <input
                type="text"
                value={originLatLng}
                placeholder="13.0821, 80.2452"
                onChange={(e) => setOriginLatLng(e.target.value)}
              />
            </label>
            <label className="field toggle">
              <input
                type="checkbox"
                checked={houseEmergency}
                onChange={(e) => setHouseEmergency(e.target.checked)}
              />
              Emergency (requests corridor)
            </label>
          </>
        )}
        <div className="trip-actions">
          <button
            className={isHouse && houseEmergency ? 'escalate-btn' : 'start-routine-btn'}
            onClick={() => startTrip(pickupMode, isHouse ? houseEmergency : false)}
          >
            Start {isHouse ? 'house call' : 'transfer'}
          </button>
          <button className="end-btn" onClick={() => setPickupMode(null)}>
            Back
          </button>
        </div>
      </div>
    )
  }

  // ---------- IDLE: TRIP CHOOSER ----------
  return (
    <div className="sos-panel">
      <button className="sos-btn" onClick={() => send('start_trip', { trip_type: 'SCENE', emergency: true })}>
        Start emergency
      </button>
      <div className="chooser-row">
        <button className="chooser-btn house" onClick={() => setPickupMode('HOUSE_CALL')}>
          🏠 House call
        </button>
        <button className="chooser-btn transfer" onClick={() => setPickupMode('TRANSFER')}>
          Transfer / transport
        </button>
      </div>
      <div className="live-note">Non-emergency trips never request signal priority.</div>
    </div>
  )
}
