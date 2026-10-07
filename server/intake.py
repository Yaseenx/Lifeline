from __future__ import annotations
"""
Multi-channel emergency intake — turns a report from ANY channel into a
dispatched incident. Channels:

  * call      — a human call-taker types the accident ADDRESS (geocoded to
                coordinates here). This is the primary channel in India.
  * whatsapp  — a bystander shares a live-location PIN (coordinates directly).
  * app       — future first-party app (coordinates directly).

Everything normalizes to (lat, lng) + type + priority, then auto-dispatches the
nearest available unit. The call-taker may override the classifier with the
type/priority they judged on the phone.
"""
from dataclasses import dataclass


# text -> (incident type, priority class). Used when the operator/bystander
# doesn't set them explicitly. Ambulance-first; fire recognised for later.
def classify(text: str) -> tuple:
    t = (text or "").lower()
    if any(k in t for k in ("fire", "smoke", "burning", "blaze")):
        return ("fire", "fire_major")
    if any(k in t for k in ("accident", "crash", "collision", "hit", "bleeding", "unconscious")):
        return ("road_accident", "code_red")
    if any(k in t for k in ("chest pain", "not breathing", "stroke", "cardiac")):
        return ("medical", "code_red")
    return ("medical", "code_red")   # default to life-threatening; downgrade on triage


@dataclass
class ReportResult:
    incident: object
    unit: object            # assigned Unit, or None if none free / geocode failed
    accepted: bool


def handle_report(dispatcher, lat: float, lng: float, text: str = "", via: str = "whatsapp",
                  incident_type: str | None = None, priority: str | None = None,
                  address: str = "") -> ReportResult:
    """Create an incident from coordinates and auto-dispatch the nearest unit.
    incident_type/priority override the text classifier (call-taker's judgment)."""
    itype, prio = classify(text)
    if incident_type:
        itype = incident_type
    if priority:
        prio = priority
    inc = dispatcher.create_incident(lat, lng, type=itype, priority=prio,
                                     reported_via=via, note=text[:280])
    if address and hasattr(inc, "address"):
        inc.address = address
    # fire incidents are recorded but not dispatched until the fire fleet exists
    unit = dispatcher.assign(inc.id) if itype != "fire" else None
    return ReportResult(incident=inc, unit=unit, accepted=unit is not None)


def _parse_latlng(s: str):
    """Accept a directly-typed 'lat, lng' (dispatch often has coordinates, and it
    works with no network). Returns (lat, lng) or None."""
    parts = (s or "").split(",")
    if len(parts) != 2:
        return None
    try:
        lat, lng = float(parts[0].strip()), float(parts[1].strip())
    except ValueError:
        return None
    if -90 <= lat <= 90 and -180 <= lng <= 180:
        return (lat, lng)
    return None


async def report_from_address(dispatcher, address: str, text: str = "", via: str = "call",
                              incident_type: str | None = None, priority: str | None = None,
                              geocoder=None) -> ReportResult:
    """Phone-call intake: the operator typed an ADDRESS or a 'lat, lng'. Coordinates
    are used directly (no network); an address is geocoded. If it can't be resolved,
    accepted=False (operator retries)."""
    coords = _parse_latlng(address)
    if coords:
        lat, lng = coords
        return handle_report(dispatcher, lat, lng, text=text or address, via=via,
                             incident_type=incident_type, priority=priority, address=address)
    if geocoder is None:
        from geocode import geocode as geocoder
    res = await geocoder(address)
    if not res:
        return ReportResult(incident=None, unit=None, accepted=False)
    lat, lng, _display = res
    return handle_report(dispatcher, lat, lng, text=text or address, via=via,
                         incident_type=incident_type, priority=priority, address=address)


def parse_whatsapp_location(payload: dict) -> dict | None:
    """Extract {lat, lng, text} from a Meta WhatsApp Business webhook payload.
    Location messages carry value.messages[].location.{latitude,longitude}."""
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        msg = value["messages"][0]
    except (KeyError, IndexError, TypeError):
        return None
    loc = msg.get("location")
    if not loc or "latitude" not in loc or "longitude" not in loc:
        return None
    text = ""
    if isinstance(msg.get("text"), dict):
        text = msg["text"].get("body", "")
    elif isinstance(loc.get("name"), str):
        text = loc["name"]
    return {"lat": float(loc["latitude"]), "lng": float(loc["longitude"]), "text": text}
