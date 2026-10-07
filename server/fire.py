from __future__ import annotations
"""
Fire response module — SCAFFOLD. Develop later; AMBULANCE is the priority now.

Priority policy (LOCKED FOR NOW): every ambulance class outranks every fire
class. This is the literal reading of "priority is for ambulance" and is a
PLACEHOLDER — a real structure fire vs. a non-urgent patient transfer is
debatable, so revisit before rollout.

This module is OPT-IN. If register() is never called, the system stays
ambulance-only, byte-for-byte as before. Fire-specific behaviour (multi-
apparatus dispatch, convoy arbitration, heavy-vehicle signal clearance) is
intentionally left as loud stubs to build later. No ambulance code path is
touched by importing this file.
"""
from dataclasses import dataclass, field
from enum import Enum

# Ranks injected into arbiter.CLASS_RANK by register(). Ambulance strictly on
# top; big gap so fire tiers have room without ever crossing ambulance.
AMBULANCE_RANKS = {"code_red": 200, "code_blue": 190}
FIRE_RANKS = {
    "fire_major": 100,     # structure fire / rescue / hazmat — many apparatus
    "fire_standard": 90,   # single-appliance response
    "fire_support": 80,    # water tender / relief / support
}


def register() -> dict:
    """Inject fire classes into the arbiter's priority table, keeping every
    ambulance class strictly above every fire class. Idempotent. Returns the
    merged table. Do NOT call until fire is actually being rolled out."""
    assert min(AMBULANCE_RANKS.values()) > max(FIRE_RANKS.values()), \
        "policy violation: ambulance must outrank fire"
    import arbiter
    arbiter.CLASS_RANK.update(AMBULANCE_RANKS)
    arbiter.CLASS_RANK.update(FIRE_RANKS)
    return arbiter.CLASS_RANK


class Apparatus(str, Enum):
    PUMP = "pump"                  # primary fire appliance
    WATER_TENDER = "water_tender"  # bulk water supply
    LADDER = "ladder"              # aerial / high-rise
    RESCUE = "rescue"              # extrication / technical rescue
    HAZMAT = "hazmat"


# Starter run cards: incident type -> apparatus required. NUMBERS ARE
# PLACEHOLDERS — calibrate against TNFRS SOPs before any real use.
RUN_CARDS: dict[str, list] = {
    "structure_fire": [Apparatus.PUMP, Apparatus.PUMP, Apparatus.WATER_TENDER, Apparatus.LADDER],
    "road_accident":  [Apparatus.RESCUE, Apparatus.PUMP],
    "rescue":         [Apparatus.RESCUE, Apparatus.PUMP],
    "hazmat":         [Apparatus.HAZMAT, Apparatus.PUMP],
    "small_fire":     [Apparatus.PUMP],
}


@dataclass
class FireApparatus:
    """One fire appliance. Will run the SAME signed-GPS unit agent as an
    ambulance and report status. SCAFFOLD — not yet wired into the engine."""
    id: str
    kind: Apparatus
    station_id: str
    cls: str = "fire_standard"
    lat: float = 0.0
    lng: float = 0.0
    status: str = "available"  # available|enroute|on_scene|returning|oos


@dataclass
class FireIncident:
    """A dispatched fire incident. Unlike an ambulance run (one unit, then a
    hospital), a fire incident pulls MULTIPLE apparatus and is sustained on
    scene with no transport leg."""
    id: str
    type: str
    lat: float
    lng: float
    required: list = field(default_factory=list)
    assigned: list = field(default_factory=list)


# ---- the genuinely fire-specific parts, intentionally NOT built yet --------

def dispatch_fire(incident: "FireIncident", fleet: list) -> list:
    """Pick apparatus from the run card, nearest-available per type.
    TODO(fire): multi-apparatus assignment, station turnout, coverage move-ups."""
    raise NotImplementedError("fire dispatch is scheduled after the ambulance build")


def clearance_profile(cls: str) -> dict:
    """Signal-clearance overrides for heavy/long fire apparatus — longer amber
    and all-red than an ambulance. TODO(fire): calibrate and wire into
    controller.JunctionFSM as per-vehicle-class timings."""
    raise NotImplementedError("fire clearance profile not yet wired into the FSM")


def convoy_owner(incident_id: str, apparatus_ids: list) -> str:
    """Fire sends several apparatus to ONE incident; the arbiter must treat the
    convoy as a SINGLE corridor owner (not trucks competing for the junction).
    TODO(fire): make the INCIDENT, not each truck, the lease owner."""
    raise NotImplementedError("convoy arbitration not yet built")
