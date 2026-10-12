"""WhatsApp delivery via Meta Business Cloud API.

Meta requires pre-approved message TEMPLATES for anything we initiate (any
message outside the 24-hour service window). On first run, every template below
must be submitted to Meta via the WhatsApp Manager and marked `active` here only
after Meta approves it.
"""

from __future__ import annotations

import httpx

from alpago.core.config import settings
from alpago.models.notification import Notification

GRAPH_API = "https://graph.facebook.com/v21.0"


# template_name -> list of body-parameter payload keys
TEMPLATES: dict[str, list[str]] = {
    "approval_pending": ["title", "submitter", "role_display"],
    "approval_decided": ["title", "outcome"],
    "offer_sent": ["candidate_name"],
    "document_expiring": ["document_type", "expiry_date"],
}


async def send_whatsapp_notification(n: Notification) -> str | None:
    if not settings.whatsapp_token or not settings.whatsapp_phone_number_id:
        return None

    phone = n.payload.get("phone")
    if not phone:
        raise ValueError(f"notification {n.id}: payload.phone required for whatsapp")

    tpl_params = TEMPLATES.get(n.template, [])
    components = [
        {
            "type": "body",
            "parameters": [{"type": "text", "text": str(n.payload.get(k, ""))} for k in tpl_params],
        }
    ]

    url = f"{GRAPH_API}/{settings.whatsapp_phone_number_id}/messages"
    body = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": n.template,
            "language": {"code": "en"},
            "components": components,
        },
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("messages", [{}])[0].get("id")
