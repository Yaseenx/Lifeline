from __future__ import annotations
"""
Real WhatsApp Business Cloud API integration (Meta).

Provides the webhook verification handshake, inbound-message parsing (reuses
intake.parse_whatsapp_location), and outbound replies via the Graph API. All
credentials come from environment variables so nothing secret is committed:

    WA_VERIFY_TOKEN     – arbitrary string you also enter in the Meta webhook UI
    WA_ACCESS_TOKEN     – permanent/temporary access token for the WhatsApp app
    WA_PHONE_NUMBER_ID  – the sending number's ID (Meta > WhatsApp > API Setup)
    WA_API_VERSION      – default v20.0

Get these at developers.facebook.com → your app → WhatsApp → API Setup. Until
they are set, the client runs in "log-only" mode (parsing still works; replies
are logged instead of sent), so the rest of the server is fully testable.
"""
import logging
import os

log = logging.getLogger("whatsapp")
GRAPH = "https://graph.facebook.com"


class WhatsAppClient:
    def __init__(self, access_token=None, phone_number_id=None,
                 verify_token=None, api_version=None):
        self.access_token = access_token or os.getenv("WA_ACCESS_TOKEN", "")
        self.phone_number_id = phone_number_id or os.getenv("WA_PHONE_NUMBER_ID", "")
        self.verify_token = verify_token or os.getenv("WA_VERIFY_TOKEN", "")
        self.api_version = api_version or os.getenv("WA_API_VERSION", "v20.0")

    @property
    def configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id)

    def verify_webhook(self, params) -> str | None:
        """Meta GET handshake: echo hub.challenge iff the verify token matches."""
        if (params.get("hub.mode") == "subscribe"
                and params.get("hub.verify_token") == self.verify_token
                and self.verify_token):
            return params.get("hub.challenge")
        return None

    async def send_text(self, to: str, body: str) -> bool:
        """Reply to a bystander over WhatsApp. Returns True on success.
        Uses stdlib urllib (no httpx dependency); the blocking POST runs in a
        thread so it never stalls the event loop."""
        if not self.configured:
            log.warning("WhatsApp not configured (WA_ACCESS_TOKEN / WA_PHONE_NUMBER_ID) "
                        "— would reply to %s: %s", to, body)
            return False
        import asyncio
        import json
        import ssl
        import urllib.request
        url = f"{GRAPH}/{self.api_version}/{self.phone_number_id}/messages"
        data = json.dumps({"messaging_product": "whatsapp", "to": to,
                           "type": "text", "text": {"body": body[:4096]}}).encode()
        headers = {"Authorization": f"Bearer {self.access_token}",
                   "Content-Type": "application/json"}

        try:
            ssl_ctx = ssl._create_unverified_context()
        except AttributeError:
            ssl_ctx = ssl.create_default_context()

        def _post() -> bool:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as r:
                    return 200 <= r.status < 300
            except Exception as e:  # network / API error must never crash the server
                log.warning("WhatsApp send error: %s", e)
                return False

        return await asyncio.get_event_loop().run_in_executor(None, _post)


def sender_of(payload: dict) -> str | None:
    """The bystander's WhatsApp number (wa_id / 'from') so we can reply."""
    try:
        msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        return msg.get("from")
    except (KeyError, IndexError, TypeError):
        return None
