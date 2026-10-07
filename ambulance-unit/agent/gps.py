import asyncio
import time
from dataclasses import dataclass


@dataclass
class GpsFix:
    lat: float = 0.0
    lng: float = 0.0
    speed_kph: float = 0.0
    heading_deg: float = 0.0
    ts: float = 0.0
    fix: bool = False


class BridgeGps:
    """REAL phone GPS path: fixes pushed from the dashboard's browser geolocation
    (navigator.geolocation) over the UI bridge. The agent's telemetry loop
    consumes them and streams signed telemetry to the server. Open the dashboard
    on a phone in the vehicle and its real GPS drives the system."""

    def __init__(self, cfg):
        self._q: asyncio.Queue = asyncio.Queue()

    def push(self, lat, lng, speed_kph=0.0, heading_deg=0.0):
        try:
            self._q.put_nowait(GpsFix(lat=float(lat), lng=float(lng),
                                      speed_kph=float(speed_kph or 0.0),
                                      heading_deg=float(heading_deg or 0.0),
                                      ts=time.time(), fix=True))
        except Exception:
            pass

    async def stream(self):
        while True:
            yield await self._q.get()


class SerialGps:
    """REAL hardware GPS: NEO-M8N over serial (needs pyserial + pynmea2). On a
    Raspberry Pi enable the UART and point GPS_SERIAL_PORT at /dev/serial0."""

    def __init__(self, cfg):
        self.port = cfg.gps_serial_port
        self.baud = cfg.gps_baud

    async def stream(self):
        import serial
        import pynmea2
        loop = asyncio.get_event_loop()
        ser = serial.Serial(self.port, self.baud, timeout=1)
        last = GpsFix()
        while True:
            line = await loop.run_in_executor(None, ser.readline)
            try:
                msg = pynmea2.parse(line.decode("ascii", errors="replace").strip())
            except Exception:
                continue
            if isinstance(msg, pynmea2.types.talker.RMC) and msg.status == "A":
                last = GpsFix(
                    lat=msg.latitude, lng=msg.longitude,
                    speed_kph=float(msg.spd_over_grnd or 0) * 1.852,
                    heading_deg=float(msg.true_course or last.heading_deg or 0),
                    ts=time.time(), fix=True,
                )
                yield last


def make_gps(cfg):
    """Real GPS only. 'serial' = NEO-M8N hardware; anything else ('phone') =
    fixes pushed from the dashboard's browser geolocation over the UI bridge.
    (The old in-code route simulator has been removed.)"""
    return SerialGps(cfg) if cfg.gps_mode == "serial" else BridgeGps(cfg)
