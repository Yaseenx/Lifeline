import asyncio
import logging
import socketio

from protocol import (EV_TELEMETRY, EV_SOS, EV_TRIP,
                      EV_HAZARD_ACK, EV_REROUTE_ACK, EV_DISPATCH_ACK)

log = logging.getLogger("cloud")


class CloudClient:
    """Authenticated Socket.IO link to the central server.

    The server owns the corridor planning and all fail-safe logic; this client only
    reports the vehicle and relays whatever the server sends back. If the link drops,
    Socket.IO keeps retrying — and per the architecture the *server* fails safe, so
    losing this link must never be able to put a junction into an unsafe state."""

    def __init__(self, url: str, auth):
        self.url = url
        self.auth = auth
        self.connected = False
        # Library auto-reconnect is OFF on purpose: it would replay the ORIGINAL
        # auth handshake, whose timestamp goes stale, so every silent retry gets
        # refused by the server (symptom: server dot stays red after a server
        # restart). connect_forever() below owns retries and mints a FRESH
        # signed handshake each attempt.
        self.sio = socketio.AsyncClient(reconnection=False)

        @self.sio.event
        async def connect():
            self.connected = True
            log.info("cloud connected")

        @self.sio.event
        async def disconnect():
            self.connected = False
            log.warning("cloud disconnected")

    def on(self, event, handler):
        self.sio.on(event, handler)

    async def connect_forever(self):
        while True:
            try:
                await self.sio.connect(
                    self.url, auth=self.auth.handshake(), transports=["websocket"]
                )
                await self.sio.wait()   # returns when the connection drops
                self.connected = False
                log.warning("cloud disconnected (reconnect in 3s)")
            except Exception as e:
                self.connected = False
                log.warning("cloud connect failed: %s (retry in 3s)", e)
            await asyncio.sleep(3)

    async def _emit(self, event, payload):
        if not self.connected:
            return
        try:
            await self.sio.emit(event, self.auth.signed(payload))
        except Exception as e:
            log.warning("emit %s failed: %s", event, e)

    async def send_telemetry(self, payload):   await self._emit(EV_TELEMETRY, payload)
    async def send_sos(self, payload):         await self._emit(EV_SOS, payload)
    async def send_trip(self, payload):        await self._emit(EV_TRIP, payload)
    async def send_hazard_ack(self, payload):  await self._emit(EV_HAZARD_ACK, payload)
    async def send_reroute_ack(self, payload): await self._emit(EV_REROUTE_ACK, payload)
    async def send_dispatch_ack(self, payload): await self._emit(EV_DISPATCH_ACK, payload)
