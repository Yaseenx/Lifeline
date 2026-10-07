import asyncio
import json
import logging
import websockets

log = logging.getLogger("ui")


class UiBridge:
    """Localhost websocket that the dashboard connects to.

    The browser never touches the cloud or the device credential; it only talks to
    this bridge. The agent pushes full state snapshots down, and receives driver
    commands (SOS, destination, condition) back up."""

    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self.clients = set()
        self._cmd_cb = None
        self._last = None

    def on_command(self, cb):
        self._cmd_cb = cb

    async def _handler(self, ws, *args):
        self.clients.add(ws)
        log.info("dashboard connected (%d total)", len(self.clients))
        try:
            if self._last is not None:
                await ws.send(json.dumps({"type": "state", "state": self._last}))
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                if data.get("type") == "command" and self._cmd_cb:
                    await self._cmd_cb(data.get("action"), data.get("payload") or {})
        finally:
            self.clients.discard(ws)
            log.info("dashboard disconnected (%d left)", len(self.clients))

    async def start(self):
        await websockets.serve(self._handler, self.host, self.port)
        log.info("UI bridge listening on ws://%s:%d", self.host, self.port)

    async def broadcast(self, state: dict):
        self._last = state
        if not self.clients:
            return
        msg = json.dumps({"type": "state", "state": state})
        await asyncio.gather(*[c.send(msg) for c in list(self.clients)],
                             return_exceptions=True)
