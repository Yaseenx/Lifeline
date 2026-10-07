import hmac
import hashlib
import json
import time


class Auth:
    """Dev-grade HMAC signing so the server can reject unauthenticated packets.

    PRODUCTION: replace the shared secret with a per-device asymmetric key that is
    provisioned at fleet registration (sign with the device private key; the server
    verifies with the matching public key). The interface below stays the same."""

    def __init__(self, device_id: str, secret: str):
        self.device_id = device_id
        self._secret = secret.encode()

    def sign(self, payload: dict) -> str:
        body = {k: v for k, v in payload.items() if k != "sig"}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        return hmac.new(self._secret, canonical, hashlib.sha256).hexdigest()

    def signed(self, payload: dict) -> dict:
        payload = dict(payload)
        payload.setdefault("ts", time.time())
        payload["sig"] = self.sign(payload)
        return payload

    def handshake(self) -> dict:
        """Auth object sent on the Socket.IO connect handshake."""
        p = {"device_id": self.device_id, "ts": time.time()}
        p["sig"] = self.sign(p)
        return p
