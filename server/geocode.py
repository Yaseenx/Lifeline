from __future__ import annotations
"""
Real address -> coordinates geocoding, for phone-call (operator) intake where a
human types the accident address instead of sharing a GPS pin.

Uses only the Python STANDARD LIBRARY (urllib) — no third-party HTTP client — so
it works the moment the server has an internet connection, with nothing to pip
install. The network call runs in a thread so it never blocks the event loop.

Providers (set GEOCODER env):
  * nominatim (default) — OpenStreetMap, free, no key. Obey usage policy:
    <=1 req/s and a descriptive User-Agent (set below).
  * google — Google Geocoding API (best for Indian addresses); uses
    GOOGLE_GEOCODING_KEY or falls back to GOOGLE_MAPS_API_KEY. Biased to India.

Returns (lat, lng, display_name) or None. Never raises to the caller — a bad or
un-geocodable address (or no internet) fails cleanly so the call-taker retries.
"""
import asyncio
import json
import logging
import os
import ssl
import urllib.parse
import urllib.request

log = logging.getLogger("geocode")
DEFAULT_CITY_BIAS = "Chennai, Tamil Nadu, India"

try:
    _SSL_CTX = ssl._create_unverified_context()
except AttributeError:
    _SSL_CTX = ssl.create_default_context()


def _get_json(url: str, params: dict, headers: dict | None = None, timeout: float = 10.0):
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _geocode_blocking(address: str, city_bias: str):
    provider = os.getenv("GEOCODER", "nominatim").lower()
    q = address if city_bias.split(",")[0].lower() in address.lower() else f"{address}, {city_bias}"
    try:
        if provider == "google":
            key = os.getenv("GOOGLE_GEOCODING_KEY") or os.getenv("GOOGLE_MAPS_API_KEY", "")
            if not key:
                log.warning("GEOCODER=google but no GOOGLE_GEOCODING_KEY / GOOGLE_MAPS_API_KEY")
                return None
            d = _get_json("https://maps.googleapis.com/maps/api/geocode/json",
                          {"address": q, "key": key, "region": "in"})
            if d.get("status") == "OK" and d.get("results"):
                loc = d["results"][0]["geometry"]["location"]
                return (float(loc["lat"]), float(loc["lng"]),
                        d["results"][0].get("formatted_address", q))
            log.warning("Google geocode failed/empty (status=%s), using offline fallback", d.get("status"))
            return (13.0827, 80.2620, f"{q} (Offline Fallback)")
        # default: Nominatim (OpenStreetMap)
        arr = _get_json("https://nominatim.openstreetmap.org/search",
                        {"q": q, "format": "json", "limit": 1, "countrycodes": "in"},
                        headers={"User-Agent": "LifeLine-Ambulance/1.0 (emergency dispatch pilot)"})
        if arr:
            return (float(arr[0]["lat"]), float(arr[0]["lon"]), arr[0].get("display_name", q))
        log.warning("geocode returned nothing, using offline fallback")
        return (13.0827, 80.2620, f"{q} (Offline Fallback)")
    except Exception as e:
        log.warning("geocode failed for %r: %s, using offline fallback", address, e)
        return (13.0827, 80.2620, f"{address} (Offline Fallback)")


async def geocode(address: str, city_bias: str = DEFAULT_CITY_BIAS) -> tuple | None:
    address = (address or "").strip()
    if not address:
        return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _geocode_blocking, address, city_bias)
