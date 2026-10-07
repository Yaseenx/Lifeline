import time
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


@dataclass
class TripState:
    active: bool = False
    trip_id: Optional[str] = None
    # SCENE | HOUSE_CALL | TRANSFER (see protocol.py trip model)
    trip_type: str = "SCENE"
    # HARD RULE: emergency=False must never lead to a preemption request.
    emergency: bool = False
    # 1 = to pickup (house call), 2 = to hospital
    leg: int = 2
    patient_onboard: bool = False
    origin_address: Optional[str] = None
    origin_lat: Optional[float] = None
    origin_lng: Optional[float] = None
    destination_id: Optional[str] = None
    destination_name: Optional[str] = None
    destination_lat: Optional[float] = None
    destination_lng: Optional[float] = None
    condition: Optional[str] = None


@dataclass
class CorridorNode:
    id: str
    name: str
    lat: float
    lng: float
    # Grant semantics (MON-8/SEC-10): the server states are passed through as-is.
    # idle | requested | queued | granted | green | rejected | red | passed
    state: str = "idle"
    eta_sec: Optional[float] = None
    green_in_s: Optional[float] = None  # server's predicted seconds to green
    controlled: Optional[bool] = None   # real controller site (J1/J2/J3) vs a live route signal


@dataclass
class CorridorState:
    status: str = "inactive"      # inactive | planning | active | clearing
    queue_position: Optional[int] = None
    safe_speed_kph: Optional[float] = None
    nodes: List[CorridorNode] = field(default_factory=list)
    path: Optional[list] = None   # server road route to the hospital ([{lat,lng}])
    dest_distance_m: Optional[float] = None  # server-computed, straight-line
    dest_eta_sec: Optional[float] = None


@dataclass
class Hazard:
    node_id: str
    type: str
    message: str
    severity: str = "warn"        # info | warn | critical
    lane: Optional[str] = None
    ts: float = 0.0


@dataclass
class VehicleState:
    device_id: str
    cloud_connected: bool = False
    gps_fix: bool = False
    lat: float = 0.0
    lng: float = 0.0
    speed_kph: float = 0.0
    heading_deg: float = 0.0
    ts: float = 0.0
    trip: TripState = field(default_factory=TripState)
    corridor: CorridorState = field(default_factory=CorridorState)
    hazards: List[Hazard] = field(default_factory=list)
    # A dispatch offered by the control centre, awaiting crew Accept/Decline.
    # {incident_id, type, priority, lat, lng, address} or None.
    pending_dispatch: Optional[Dict[str, Any]] = None

    def update_gps(self, fix) -> None:
        self.gps_fix = fix.fix
        if fix.fix:
            self.lat, self.lng = fix.lat, fix.lng
            self.speed_kph, self.heading_deg = fix.speed_kph, fix.heading_deg
        self.ts = fix.ts

    def telemetry(self) -> Dict[str, Any]:
        """Compact payload sent up to the server at the telemetry rate."""
        return {
            "device_id": self.device_id,
            # fix=False means "no GPS yet" — the server must NOT treat the 0,0
            # default as a real position (that would place us off the coast of
            # Africa and lock the plausibility gate onto null island).
            "fix": self.gps_fix,
            "lat": round(self.lat, 6),
            "lng": round(self.lng, 6),
            "speed_kph": round(self.speed_kph, 1),
            "heading_deg": round(self.heading_deg, 1),
            "trip_id": self.trip.trip_id,
            "trip_type": self.trip.trip_type if self.trip.active else None,
            "leg": self.trip.leg if self.trip.active else None,
            # sos is true ONLY for active emergency trips (non-emergency never preempts)
            "sos": self.trip.active and self.trip.emergency,
            "ts": self.ts,
        }

    def trip_payload(self) -> Dict[str, Any]:
        """Full trip description sent on vehicle:trip."""
        t = self.trip
        return {
            "device_id": self.device_id,
            "trip_id": t.trip_id,
            "trip_type": t.trip_type,
            "emergency": t.emergency,
            "leg": t.leg,
            "patient_onboard": t.patient_onboard,
            "origin": {"address": t.origin_address, "lat": t.origin_lat, "lng": t.origin_lng},
            "destination_id": t.destination_id,
            "destination_name": t.destination_name,
            "destination_lat": t.destination_lat,
            "destination_lng": t.destination_lng,
            "condition": t.condition,
        }

    def snapshot(self) -> Dict[str, Any]:
        """Full state pushed to the dashboard."""
        return asdict(self)
