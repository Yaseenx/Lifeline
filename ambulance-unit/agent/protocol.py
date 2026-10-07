"""Message contract shared with the dashboard (dashboard/src/protocol.ts) and the
central server. Keep this file and its TypeScript mirror in sync."""

# --- Cloud events: agent -> server ---
EV_TELEMETRY   = "vehicle:telemetry"
EV_SOS         = "vehicle:sos"
EV_TRIP        = "vehicle:trip"
EV_HAZARD_ACK  = "vehicle:hazard_ack"
EV_REROUTE_ACK = "vehicle:reroute_ack"
EV_DISPATCH_ACK = "vehicle:dispatch_ack"   # crew accepted/declined an assignment

# --- Cloud events: server -> agent ---
EV_CORRIDOR_UPDATE = "corridor:update"
EV_HAZARD_ALERT    = "hazard:alert"
EV_ROUTE_SUGGEST   = "route:suggest"
EV_TRIP_ACK        = "trip:ack"
EV_DISPATCH_ASSIGN = "dispatch:assign"     # server -> agent: you've been dispatched

# --- Local UI-bridge message types (JSON over the localhost websocket) ---
MSG_STATE   = "state"     # agent -> ui : full VehicleState snapshot
MSG_COMMAND = "command"   # ui -> agent : {action, payload}

# --- Trip model ---
# trip_type x emergency x leg:
#   SCENE      - emergency at an accident scene (1 leg: to hospital)
#   HOUSE_CALL - pickup at a residence (2 legs: to residence, then to hospital);
#                may be emergency or non-emergency
#   TRANSFER   - inter-facility / scheduled transport (non-emergency by default)
# HARD RULE: a non-emergency trip NEVER requests preemption. The agent only
# emits vehicle:sos when trip.emergency is true; the server's arbiter must never
# see a non-emergency trip as a corridor candidate.
TRIP_SCENE      = "SCENE"
TRIP_HOUSE_CALL = "HOUSE_CALL"
TRIP_TRANSFER   = "TRANSFER"

# UI command actions
CMD_SOS             = "sos"              # {active: bool}  (compat: emergency scene shortcut)
CMD_START_TRIP      = "start_trip"       # {trip_type, emergency, origin_address?, origin_lat?, origin_lng?}
CMD_END_TRIP        = "end_trip"         # {}
CMD_SET_TRIP        = "set_trip"         # {destination_id, destination_name, condition}
CMD_PATIENT_ONBOARD = "patient_onboard"  # {} house-call leg 1 -> leg 2
CMD_ESCALATE        = "escalate"         # {condition?} non-emergency -> emergency (SOS from current position)
CMD_DEESCALATE      = "deescalate"       # {} emergency -> non-emergency (corridor released)
CMD_ACK_HAZARD      = "ack_hazard"       # {node_id}
CMD_ACCEPT_REROUTE  = "accept_reroute"   # {}
CMD_GPS_FIX         = "gps_fix"          # {lat, lng, speed_kph?, heading_deg?} real phone GPS from the dashboard
CMD_ACCEPT_DISPATCH  = "accept_dispatch"  # crew accepts the pending assignment -> starts the emergency trip
CMD_DECLINE_DISPATCH = "decline_dispatch" # crew declines -> unit freed for reassignment
