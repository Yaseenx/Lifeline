import asyncio
import logging
import time
import uuid

from config import Config
from state import VehicleState, CorridorNode, CorridorState, Hazard
from auth import Auth
from gps import make_gps
from cloud_client import CloudClient
from ui_bridge import UiBridge
import protocol as P

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-6s %(levelname)-7s %(message)s",
)
log = logging.getLogger("main")


class AmbulanceAgent:
    """Orchestrates GPS -> cloud -> dashboard for one ambulance unit.

    Trip model: SCENE / HOUSE_CALL / TRANSFER, each emergency or not.
    HARD RULE: non-emergency trips never emit vehicle:sos and any corridor
    pushed for them is refused — preemption is for emergencies only."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.state = VehicleState(device_id=cfg.device_id)
        self.auth = Auth(cfg.device_id, cfg.device_secret)
        self.gps = make_gps(cfg)
        self.cloud = CloudClient(cfg.cloud_url, self.auth)
        self.bridge = UiBridge(cfg.ui_host, cfg.ui_port)
        self._condition_timer = None

        # server -> agent
        self.cloud.on(P.EV_CORRIDOR_UPDATE, self._on_corridor)
        self.cloud.on(P.EV_HAZARD_ALERT, self._on_hazard)
        self.cloud.on(P.EV_TRIP_ACK, self._on_trip_ack)
        self.cloud.on(P.EV_DISPATCH_ASSIGN, self._on_dispatch_assign)
        # ui -> agent
        self.bridge.on_command(self._on_command)

    async def _push_ui(self):
        self.state.cloud_connected = self.cloud.connected
        await self.bridge.broadcast(self.state.snapshot())

    # ---------- cloud handlers ----------
    async def _on_corridor(self, data):
        # Defense in depth for the hard rule: a non-emergency trip must never
        # ride a corridor, even if the server (or a bug) offers one.
        if not (self.state.trip.active and self.state.trip.emergency):
            log.warning("corridor update refused: no active emergency trip")
            return
        nodes = [
            CorridorNode(
                id=str(n.get("id", "")), name=n.get("name", ""),
                lat=float(n.get("lat", 0)), lng=float(n.get("lng", 0)),
                state=n.get("state", "idle"), eta_sec=n.get("eta_sec"),
                green_in_s=n.get("green_in_s"), controlled=n.get("controlled"),
            )
            for n in data.get("nodes", [])
        ]
        self.state.corridor = CorridorState(
            status=data.get("status", "active"),
            queue_position=data.get("queue_position"),
            safe_speed_kph=data.get("safe_speed_kph"),
            nodes=nodes,
            path=data.get("path"),   # server's road route -> drawn on the map
            dest_distance_m=data.get("dest_distance_m"),
            dest_eta_sec=data.get("dest_eta_sec"),
        )
        if data.get("trip_id"):
            self.state.trip.trip_id = data["trip_id"]
        await self._push_ui()

    async def _on_hazard(self, data):
        hz = Hazard(
            node_id=data.get("node_id", ""), type=data.get("type", "obstacle"),
            message=data.get("message", ""), severity=data.get("severity", "warn"),
            lane=data.get("lane"), ts=time.time(),
        )
        self.state.hazards = [hz] + self.state.hazards[:4]
        await self._push_ui()

    async def _on_trip_ack(self, data):
        if data.get("trip_id"):
            self.state.trip.trip_id = data["trip_id"]
        await self._push_ui()

    async def _on_dispatch_assign(self, data):
        """Control centre dispatched this unit — offer it to the crew (Accept/Decline)."""
        self.state.pending_dispatch = {
            "incident_id": data.get("incident_id"),
            "type": data.get("type"),
            "priority": data.get("priority"),
            "lat": data.get("lat"), "lng": data.get("lng"),
            "address": data.get("address"),
        }
        log.info("dispatch offered: %s", self.state.pending_dispatch)
        await self._push_ui()

    # ---------- ui command handler ----------
    async def _on_command(self, action, payload):
        log.info("command %s %s", action, payload)
        t = self.state.trip
        if action == P.CMD_SOS:
            # Compat shortcut: SOS on = emergency scene trip; SOS off = end trip.
            if payload.get("active"):
                await self._start_trip(P.TRIP_SCENE, emergency=True, payload=payload)
            else:
                await self._end_trip()
        elif action == P.CMD_START_TRIP:
            await self._start_trip(
                str(payload.get("trip_type") or P.TRIP_SCENE),
                emergency=bool(payload.get("emergency")),
                payload=payload,
            )
        elif action == P.CMD_END_TRIP:
            await self._end_trip()
        elif action == P.CMD_PATIENT_ONBOARD:
            if t.active and t.leg == 1:
                t.leg = 2
                t.patient_onboard = True
                await self.cloud.send_trip(self.state.trip_payload())
        elif action == P.CMD_ESCALATE:
            if t.active and not t.emergency:
                t.emergency = True
                if payload.get("condition"):
                    t.condition = payload["condition"]
                elif not t.condition:
                    self._start_condition_timer()
                await self.cloud.send_trip(self.state.trip_payload())
                await self._send_sos_state()
        elif action == P.CMD_DEESCALATE:
            if t.active and t.emergency:
                t.emergency = False
                self._cancel_condition_timer()
                self.state.corridor = CorridorState()  # corridor released immediately
                await self.cloud.send_trip(self.state.trip_payload())
                await self._send_sos_state()
        elif action == P.CMD_SET_TRIP:
            t.destination_id = payload.get("destination_id")
            t.destination_name = payload.get("destination_name")
            lat, lng = payload.get("destination_lat"), payload.get("destination_lng")
            t.destination_lat = float(lat) if isinstance(lat, (int, float)) else None
            t.destination_lng = float(lng) if isinstance(lng, (int, float)) else None
            if payload.get("condition"):
                t.condition = payload["condition"]
                self._cancel_condition_timer()
            await self.cloud.send_trip(self.state.trip_payload())
        elif action == P.CMD_ACK_HAZARD:
            nid = payload.get("node_id")
            self.state.hazards = [h for h in self.state.hazards if h.node_id != nid]
            await self.cloud.send_hazard_ack({"device_id": self.cfg.device_id, "node_id": nid})
        elif action == P.CMD_ACCEPT_REROUTE:
            await self.cloud.send_reroute_ack({"device_id": self.cfg.device_id, "accepted": True})
        elif action == P.CMD_ACCEPT_DISPATCH:
            pd = self.state.pending_dispatch
            if pd:
                self.state.pending_dispatch = None
                t.condition = pd.get("priority") or t.condition
                t.trip_id = pd.get("incident_id") or t.trip_id
                # accepting -> RESPOND to the accident first (leg 1), then transport
                # to the hospital the crew selects (leg 2). The accident location
                # comes from the dispatch, so the map routes to it, not the hospital.
                await self._start_trip(P.TRIP_SCENE, emergency=True, payload={
                    "origin_lat": pd.get("lat"), "origin_lng": pd.get("lng"),
                    "origin_address": pd.get("address"),
                })
        elif action == P.CMD_DECLINE_DISPATCH:
            pd = self.state.pending_dispatch
            self.state.pending_dispatch = None
            if pd:
                await self.cloud.send_dispatch_ack({"device_id": self.cfg.device_id,
                                                    "accepted": False,
                                                    "incident_id": pd.get("incident_id")})
        elif action == P.CMD_GPS_FIX:
            # real phone GPS pushed from the dashboard (browser geolocation)
            if hasattr(self.gps, "push"):
                self.gps.push(payload.get("lat", 0), payload.get("lng", 0),
                              payload.get("speed_kph", 0), payload.get("heading_deg", 0))
            return
        await self._push_ui()

    # ---------- trip lifecycle ----------
    async def _start_trip(self, trip_type: str, emergency: bool, payload: dict):
        t = self.state.trip
        t.active = True
        t.trip_type = trip_type
        t.emergency = emergency
        t.trip_id = t.trip_id or str(uuid.uuid4())
        t.patient_onboard = False
        t.origin_address = payload.get("origin_address")
        t.origin_lat = payload.get("origin_lat")
        t.origin_lng = payload.get("origin_lng")
        # Two legs whenever the unit must reach a location before the hospital:
        # a house-call pickup, OR a dispatched accident (origin = accident site).
        # leg 1 = drive to that location; leg 2 = transport to the hospital.
        responding = t.origin_lat is not None and t.origin_lng is not None
        t.leg = 1 if (trip_type == P.TRIP_HOUSE_CALL or responding) else 2
        if emergency and not t.condition:
            self._start_condition_timer()
        await self.cloud.send_trip(self.state.trip_payload())
        await self._send_sos_state()

    async def _end_trip(self):
        self._cancel_condition_timer()
        was_emergency = self.state.trip.emergency and self.state.trip.active
        self.state.trip = type(self.state.trip)()  # fresh TripState
        self.state.corridor = CorridorState()
        if was_emergency:
            await self._send_sos_state()
        await self.cloud.send_trip(self.state.trip_payload())

    async def _send_sos_state(self):
        """vehicle:sos reflects ONLY active emergency trips (the hard rule lives here)."""
        t = self.state.trip
        await self.cloud.send_sos({
            "device_id": self.cfg.device_id,
            "active": bool(t.active and t.emergency),
            "trip_id": t.trip_id,
            "trip_type": t.trip_type,
            "leg": t.leg,
            "destination_id": t.destination_id,
            "condition": t.condition,
        })

    # ---------- condition default timer ----------
    def _start_condition_timer(self):
        self._cancel_condition_timer()
        self._condition_timer = asyncio.create_task(self._condition_timeout())

    def _cancel_condition_timer(self):
        if self._condition_timer:
            self._condition_timer.cancel()
            self._condition_timer = None

    async def _condition_timeout(self):
        try:
            await asyncio.sleep(self.cfg.condition_timeout_sec)
            t = self.state.trip
            if t.active and t.emergency and not t.condition:
                t.condition = self.cfg.default_condition
                log.info("no condition entered; defaulting to %s", self.cfg.default_condition)
                await self.cloud.send_trip(self.state.trip_payload())
                await self._push_ui()
        except asyncio.CancelledError:
            pass

    # ---------- main loop ----------
    async def _gps_loop(self):
        interval = 1.0 / max(0.2, self.cfg.telemetry_hz)
        last_tx = 0.0
        async for fix in self.gps.stream():
            self.state.update_gps(fix)
            await self._push_ui()
            now = time.time()
            if now - last_tx >= interval:
                last_tx = now
                await self.cloud.send_telemetry(self.state.telemetry())

    async def run(self):
        await self.bridge.start()
        asyncio.create_task(self.cloud.connect_forever())
        log.info("ambulance agent up (device=%s, gps=%s, cloud=%s)",
                 self.cfg.device_id, self.cfg.gps_mode, self.cfg.cloud_url)
        await self._gps_loop()


async def amain():
    cfg = Config.load()
    await AmbulanceAgent(cfg).run()

def main():
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
