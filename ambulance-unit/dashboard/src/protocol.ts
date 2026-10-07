// Mirror of agent/protocol.py + agent/state.py. Keep the two in sync.

// Grant semantics (MON-8 / SEC-10): the driver must NEVER assume right-of-way.
// 'granted' is the only state that means the junction is explicitly cleared for
// this vehicle; 'queued' / 'requested' / 'rejected' all mean OBEY THE SIGNALS.
export type NodeState =
  | 'idle'
  | 'requested'
  | 'queued'
  | 'granted'
  | 'green'
  | 'rejected'
  | 'red'
  | 'passed'

export interface CorridorNode {
  id: string
  name: string
  lat: number
  lng: number
  state: NodeState
  eta_sec: number | null
  green_in_s?: number | null // server's predicted seconds until green
  controlled?: boolean       // true = real controller site (J1/J2/J3); else a live route signal
}

export interface CorridorState {
  status: 'inactive' | 'planning' | 'active' | 'clearing'
  queue_position: number | null
  safe_speed_kph: number | null
  nodes: CorridorNode[]
  // Optional road-following geometry of the route (drawn as the corridor line).
  // Falls back to a straight line through the nodes when absent.
  path?: { lat: number; lng: number }[] | null
  // Live remaining distance (m) and ETA (s) to the destination. ETA is null
  // when stationary (can't estimate arrival from zero speed).
  dest_distance_m?: number | null
  dest_eta_sec?: number | null
}

// Trip model: type x emergency x leg. HARD RULE: a non-emergency trip never
// requests preemption — the agent only emits vehicle:sos when emergency=true.
export type TripType = 'SCENE' | 'HOUSE_CALL' | 'TRANSFER'

export interface TripState {
  active: boolean
  trip_id: string | null
  trip_type: TripType
  emergency: boolean
  leg: 1 | 2 // 1 = to pickup (house call), 2 = to hospital
  patient_onboard: boolean
  origin_address: string | null
  origin_lat: number | null
  origin_lng: number | null
  destination_id: string | null
  destination_name: string | null
  destination_lat?: number | null
  destination_lng?: number | null
  condition: string | null
}

export interface Hazard {
  node_id: string
  type: string
  message: string
  severity: 'info' | 'warn' | 'critical'
  lane: string | null
  ts: number
}

export interface PendingDispatch {
  incident_id: string
  type: string
  priority: string
  lat: number
  lng: number
  address: string
}

export interface VehicleState {
  device_id: string
  cloud_connected: boolean
  gps_fix: boolean
  lat: number
  lng: number
  speed_kph: number
  heading_deg: number
  ts: number
  trip: TripState
  corridor: CorridorState
  hazards: Hazard[]
  // A dispatch offered by the control centre, awaiting crew Accept/Decline.
  pending_dispatch?: PendingDispatch | null
}

// UI -> agent command actions (match agent/protocol.py)
export const CMD = {
  SOS: 'sos', // compat: emergency scene shortcut
  START_TRIP: 'start_trip', // {trip_type, emergency, origin_address?, origin_lat?, origin_lng?}
  END_TRIP: 'end_trip',
  SET_TRIP: 'set_trip',
  PATIENT_ONBOARD: 'patient_onboard', // house-call leg 1 -> 2
  ESCALATE: 'escalate', // {condition?} non-emergency -> emergency
  DEESCALATE: 'deescalate', // emergency -> non-emergency (corridor releases)
  ACK_HAZARD: 'ack_hazard',
  ACCEPT_REROUTE: 'accept_reroute',
  ACCEPT_DISPATCH: 'accept_dispatch',
  DECLINE_DISPATCH: 'decline_dispatch',
} as const
