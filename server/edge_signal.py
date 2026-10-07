from __future__ import annotations
"""
Edge signal node — runs ON a Raspberry Pi at ONE junction.

Connects to the central server's live state feed, reads the commanded lamp state
for THIS junction, and drives real LEDs via GpioLampDriver. It has its OWN local
WATCHDOG: if commands stop arriving (server down, cable cut, Wi-Fi drop) it
flashes red on its own — the field-side dead-man that guarantees no stuck green
(the C3 fix: software at the centre is never the only thing keeping traffic safe).

Run on the Pi (one per junction):
  SERVER_WS_URL=ws://<server-ip>:4000/ws JUNCTION_ID=J1 python3 edge_signal.py

Pin map via env PINS (JSON) or the default below. Deps: websockets + gpiozero
(on the Pi). Off-Pi it still runs, driving the log-only GpioLampDriver.
"""
import asyncio
import json
import logging
import os
import time

from gpio_driver import GpioLampDriver

logging.basicConfig(level=logging.INFO, format="%(asctime)s edge %(levelname)s %(message)s")
log = logging.getLogger("edge")

DEFAULT_PINS = {"ns": {"red": 17, "amber": 27, "green": 22},
                "ew": {"red": 23, "amber": 24, "green": 25}}


class EdgeSignal:
    """Pure, testable core: turn a server snapshot into a lamp command, and
    enforce the local watchdog. No network here (see run() for the transport)."""

    def __init__(self, jid: str, driver, watchdog_s: float = 1.0, clock=time.monotonic):
        self.jid = jid
        self.driver = driver
        self.watchdog_s = watchdog_s
        self.clock = clock
        self.last_cmd = 0.0
        self.received = False

    def on_snapshot(self, snap: dict) -> None:
        j = next((x for x in (snap.get("junctions") or []) if x.get("id") == self.jid), None)
        if not j:
            return
        self.last_cmd = self.clock()
        self.received = True
        lamps = j.get("lamps") or {}
        if j.get("mode") == "FAULT" or lamps.get("ns") == "flash" or lamps.get("ew") == "flash":
            self.driver.flash_red(j.get("fault") or "server reported FAULT")
        else:
            self.driver.apply(lamps)

    def check_watchdog(self, now: float | None = None) -> bool:
        """If we've heard nothing for too long, flash red. Returns True if tripped."""
        now = self.clock() if now is None else now
        if self.received and (now - self.last_cmd) > self.watchdog_s:
            self.driver.flash_red(f"comms loss {now - self.last_cmd:.1f}s — no command")
            return True
        return False


async def run(url: str, jid: str, driver, watchdog_s: float = 1.0) -> None:
    import websockets  # lazy: the pure core above needs no transport
    node = EdgeSignal(jid, driver, watchdog_s)

    async def watchdog():
        while True:
            await asyncio.sleep(watchdog_s / 2)
            node.check_watchdog()

    asyncio.create_task(watchdog())
    while True:
        try:
            async with websockets.connect(url) as ws:
                log.info("connected to %s as %s", url, jid)
                async for raw in ws:
                    try:
                        node.on_snapshot(json.loads(raw))
                    except Exception:
                        continue
        except Exception as e:
            log.warning("link down (%s) — flashing red, retrying in 2s", e)
            driver.flash_red("link down")
            await asyncio.sleep(2)


def main():
    jid = os.getenv("JUNCTION_ID", "J1")
    url = os.getenv("SERVER_WS_URL", "ws://127.0.0.1:4000/ws")
    pins = json.loads(os.getenv("PINS", json.dumps(DEFAULT_PINS)))
    driver = GpioLampDriver(jid, pins)
    asyncio.run(run(url, jid, driver, float(os.getenv("WATCHDOG_S", "1.0"))))


if __name__ == "__main__":
    main()
