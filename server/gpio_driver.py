from __future__ import annotations
"""
Real signal LampDriver for a Raspberry Pi LED traffic-light model.

Implements the signal_node.LampDriver interface, so an embedded IntelligentSignal
drives REAL red/amber/green LEDs at a bench-model junction. On a Pi it uses
gpiozero; off-Pi (no GPIO library) it falls back to a log-only stub so the code
still imports and runs anywhere for development.

Wiring (per junction head = 6 LEDs): NS = red,amber,green ; EW = red,amber,green.
Pass a pin map of BCM pins:

    pins = {"ns": {"red": 17, "amber": 27, "green": 22},
            "ew": {"red": 23, "amber": 24, "green": 25}}
    driver = GpioLampDriver("J1", pins)

One driver per junction. With three junctions use three Pis, or one Pi with an
MCP23017 I/O expander (18 lines). The hardware conflict monitor (MMU) on the
model — or the wiring itself — remains the physical last line of safety.
"""
import logging

log = logging.getLogger("gpio")

try:
    from gpiozero import LED
    _HAVE_GPIO = True
except Exception:
    _HAVE_GPIO = False

_HEADS = ("ns", "ew")
_COLORS = ("red", "amber", "green")


class GpioLampDriver:
    """Concrete LampDriver: apply(lamps) and flash_red(why)."""

    def __init__(self, jid: str, pins: dict, active_high: bool = True):
        self.jid = jid
        self.pins = pins
        self._leds = {}
        if _HAVE_GPIO:
            for head in _HEADS:
                for color in _COLORS:
                    pin = pins.get(head, {}).get(color)
                    if pin is not None:
                        self._leds[(head, color)] = LED(pin, active_high=active_high)
            log.info("[%s] GPIO LampDriver ready on pins %s", jid, pins)
        else:
            log.warning("[%s] gpiozero unavailable — LampDriver in LOG-ONLY mode", jid)

    def _set(self, ns: str, ew: str) -> None:
        want = {("ns", "red"): ns == "red", ("ns", "amber"): ns == "amber",
                ("ns", "green"): ns == "green", ("ew", "red"): ew == "red",
                ("ew", "amber"): ew == "amber", ("ew", "green"): ew == "green"}
        if _HAVE_GPIO:
            for key, on in want.items():
                led = self._leds.get(key)
                if led is not None:
                    led.on() if on else led.off()
        else:
            log.info("[%s] NS=%-5s EW=%-5s", self.jid, ns, ew)

    # ---- signal_node.LampDriver interface ----
    def apply(self, lamps: dict) -> None:
        self._set(lamps.get("ns", "red"), lamps.get("ew", "red"))

    def flash_red(self, why: str = "") -> None:
        # Safe state on the model: both directions solid red. The physical
        # conflict monitor enforces this independently of software.
        self._set("red", "red")
        log.warning("[%s] FLASH-RED (latched): %s", self.jid, why)

    def all_off(self) -> None:
        if _HAVE_GPIO:
            for led in self._leds.values():
                led.off()
