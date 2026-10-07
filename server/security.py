from __future__ import annotations
"""Ingress security (SEC-1,3,4 dev-grade): HMAC signature, freshness window,
replay cache. Mirrors the vehicle agent's auth.py signing. Per-device shared
secrets come from config; production swaps in per-device asymmetric keys with
the same interface.
"""
import hashlib
import hmac
import json
import time


class Ingress:
    def __init__(self, devices: dict[str, str], freshness_s: float = 5.0):
        self.devices = devices
        self.freshness_s = freshness_s
        self._seen: dict[str, float] = {}  # sig -> expiry (replay cache)

    def _sign(self, secret: str, payload: dict) -> str:
        body = {k: v for k, v in payload.items() if k != "sig"}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        return hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()

    def verify(self, payload: dict, now: float | None = None) -> tuple[bool, str]:
        now = time.time() if now is None else now
        if not isinstance(payload, dict):
            return False, "not a dict"
        dev = payload.get("device_id")
        sig = payload.get("sig")
        ts = payload.get("ts")
        if dev not in self.devices:
            return False, f"unknown device {dev!r}"
        if not sig or not isinstance(ts, (int, float)):
            return False, "missing sig/ts"
        if abs(now - float(ts)) > self.freshness_s:
            return False, f"stale ts ({now - float(ts):+.1f}s)"
        if hmac.compare_digest(self._sign(self.devices[dev], payload), sig) is False:
            return False, "bad signature"
        # replay cache (byte-identical replays)
        self._prune(now)
        if sig in self._seen:
            return False, "replay"
        self._seen[sig] = now + self.freshness_s * 2
        return True, "ok"

    def _prune(self, now: float) -> None:
        if len(self._seen) > 4096:
            self._seen = {s: e for s, e in self._seen.items() if e > now}
