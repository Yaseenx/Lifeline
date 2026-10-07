import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


@dataclass
class Config:
    cloud_url: str
    device_id: str
    device_secret: str
    ui_host: str
    ui_port: int
    gps_mode: str            # 'phone' (browser GPS via dashboard) | 'serial' (NEO-M8N)
    gps_serial_port: str
    gps_baud: int
    telemetry_hz: float
    home_lat: float
    home_lng: float
    default_condition: str
    condition_timeout_sec: float

    @classmethod
    def load(cls) -> "Config":
        g = os.getenv
        return cls(
            cloud_url=g("CLOUD_URL", "http://localhost:4000"),
            device_id=g("DEVICE_ID", "AMB-DEV-001"),
            device_secret=g("DEVICE_SECRET", "change-me-dev-secret"),
            ui_host=g("UI_BRIDGE_HOST", "127.0.0.1"),
            ui_port=int(g("UI_BRIDGE_PORT", "8765")),
            gps_mode=g("GPS_MODE", "phone"),
            gps_serial_port=g("GPS_SERIAL_PORT", "/dev/serial0"),
            gps_baud=int(g("GPS_BAUD", "9600")),
            telemetry_hz=float(g("TELEMETRY_HZ", "1")),
            home_lat=float(g("HOME_LAT", "13.0827")),
            home_lng=float(g("HOME_LNG", "80.2707")),
            # Unknown emergency defaults to the SAFE assumption (life-threatening).
            # Must be a value the dashboard knows: code_red | code_blue.
            default_condition=g("DEFAULT_CONDITION", "code_red"),
            condition_timeout_sec=float(g("CONDITION_TIMEOUT_SEC", "10")),
        )
