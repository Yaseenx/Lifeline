from __future__ import annotations
"""Hospital registry + bed-availability store for the hospital console.

The registry mirrors the ambulance dashboard's curated list (dashboard/src/
hospitals.ts) so a trip's destination_id resolves to the same hospital here.
Bed availability is operator-entered on the hospital console and persisted to
data/hospital_beds.json so it survives restarts.

Pure/stdlib; no engine import (the endpoints combine this with the live snapshot).
Every function is safe if the store file is missing.
"""
import json
import os
import time

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "hospital_beds.json")

# id, name, lat, lng, specialty (None = general adult ED). Mirrors hospitals.ts.
HOSPITALS = [
    {"id": "apollo-greams-road", "name": "Apollo Hospitals, Greams Road", "lat": 13.0631824, "lng": 80.2515375, "specialty": None},
    {"id": "miot-international", "name": "MIOT International, Manapakkam", "lat": 13.0213892, "lng": 80.1857828, "specialty": None},
    {"id": "gleneagles-global-health-city", "name": "Gleneagles Global Health City, Perumbakkam", "lat": 12.8978488, "lng": 80.2061841, "specialty": None},
    {"id": "mgm-healthcare", "name": "MGM Healthcare, Aminjikarai", "lat": 13.0709761, "lng": 80.2216656, "specialty": None},
    {"id": "kauvery-alwarpet", "name": "Kauvery Hospital, Alwarpet", "lat": 13.038238, "lng": 80.2571361, "specialty": None},
    {"id": "sims-vadapalani", "name": "SIMS Hospital, Vadapalani", "lat": 13.0516924, "lng": 80.2117546, "specialty": None},
    {"id": "srmc-porur", "name": "Sri Ramachandra Medical Centre, Porur", "lat": 13.0391373, "lng": 80.1434689, "specialty": None},
    {"id": "rela-chromepet", "name": "Dr. Rela Institute, Chromepet", "lat": 12.9549235, "lng": 80.1388459, "specialty": None},
    {"id": "mgm-malar-adyar", "name": "MGM Malar (ex-Fortis), Adyar", "lat": 13.0101544, "lng": 80.258616, "specialty": None},
    {"id": "madras-medical-mission", "name": "Madras Medical Mission, Mogappair", "lat": 13.0859697, "lng": 80.187141, "specialty": None},
    {"id": "frontier-lifeline", "name": "Frontier Lifeline (cardiac), Mogappair", "lat": 13.087721, "lng": 80.185609, "specialty": "cardiac"},
    {"id": "rgggh-mmc", "name": "Rajiv Gandhi Govt. General Hospital (MMC)", "lat": 13.0814162, "lng": 80.2775787, "specialty": None},
    {"id": "stanley-mch", "name": "Govt. Stanley Medical College Hospital", "lat": 13.1059369, "lng": 80.2852016, "specialty": None},
    {"id": "kilpauk-mch", "name": "Govt. Kilpauk Medical College Hospital", "lat": 13.0783427, "lng": 80.2438901, "specialty": None},
    {"id": "royapettah-gh", "name": "Govt. Royapettah Hospital", "lat": 13.0552786, "lng": 80.2648512, "specialty": None},
    {"id": "kalaignar-kcssh-guindy", "name": "Kalaignar Centenary Super Speciality, Guindy", "lat": 13.0151079, "lng": 80.2155023, "specialty": None},
    {"id": "tngmssh-omandurar", "name": "TN Govt Multi Super Speciality, Omandurar", "lat": 13.0691876, "lng": 80.2737108, "specialty": None},
    {"id": "ich-egmore", "name": "Institute of Child Health, Egmore (paediatric)", "lat": 13.07349, "lng": 80.2569271, "specialty": "paediatric"},
    {"id": "iog-egmore", "name": "Institute of Obstetrics & Gynaecology, Egmore", "lat": 13.0714838, "lng": 80.2589166, "specialty": "obgyn"},
]
_BY_ID = {h["id"]: h for h in HOSPITALS}

_DEFAULT_BEDS = {"beds_available": None, "beds_total": None, "icu_available": None,
                 "ed_open": True, "note": "", "updated": None}

_beds: dict = {}


def _save() -> None:
    try:
        os.makedirs(os.path.dirname(_DATA), exist_ok=True)
        with open(_DATA, "w", encoding="utf-8") as f:
            json.dump(_beds, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # persistence is best-effort; never break the request


def _load() -> None:
    global _beds
    try:
        with open(_DATA, "r", encoding="utf-8") as f:
            _beds = json.load(f)
    except Exception:
        _beds = {}


_load()


def get(hid):
    return _BY_ID.get(hid)


def beds(hid) -> dict:
    b = dict(_DEFAULT_BEDS)
    b.update(_beds.get(hid, {}))
    return b


def _as_int(v):
    try:
        return None if v in (None, "") else max(0, int(v))
    except (TypeError, ValueError):
        return None


def set_beds(hid, beds_available=None, beds_total=None, icu_available=None,
             ed_open=None, note=None) -> dict:
    rec = dict(_beds.get(hid, {}))
    if beds_available is not None: rec["beds_available"] = _as_int(beds_available)
    if beds_total is not None:     rec["beds_total"] = _as_int(beds_total)
    if icu_available is not None:  rec["icu_available"] = _as_int(icu_available)
    if ed_open is not None:        rec["ed_open"] = bool(ed_open)
    if note is not None:           rec["note"] = str(note)[:200]
    rec["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _beds[hid] = rec
    _save()
    return beds(hid)


def list_hospitals() -> list:
    return [dict(h) for h in HOSPITALS]


def list_with_beds() -> list:
    return [{**h, "beds": beds(h["id"])} for h in HOSPITALS]
