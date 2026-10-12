"""Email delivery via Resend.

Templates are plain Jinja2 for now — React Email templates come once the frontend
pipeline is wired up. One stable callable: `send_email_notification(notification)`.
"""

from __future__ import annotations

from typing import Any

import httpx
from jinja2 import Environment, PackageLoader, select_autoescape

from alpago.core.config import settings
from alpago.models.notification import Notification

RESEND_API_URL = "https://api.resend.com/emails"

_env = Environment(
    loader=PackageLoader("alpago", "integrations/templates"),
    autoescape=select_autoescape(["html", "xml"]),
)

# Each template has a subject expression and an html template file.
TEMPLATES: dict[str, dict[str, Any]] = {
    "approval_pending": {
        "subject": "Needs your approval: {{ title }}",
        "html": "approval_pending.html",
    },
    "approval_decided": {
        "subject": "Your request was {{ outcome }}: {{ title }}",
        "html": "approval_decided.html",
    },
    "offer_sent": {
        "subject": "Your offer from Alpago",
        "html": "offer_sent.html",
    },
    "document_expiring": {
        "subject": "Document expiring: {{ document_type }}",
        "html": "document_expiring.html",
    },
    "generic": {
        "subject": "Alpago HR: {{ title }}",
        "html": "generic.html",
    },
}


async def send_email_notification(n: Notification) -> str | None:
    """Send one email via Resend. Returns the Resend id, or None in dev with no key."""
    if not settings.resend_api_key:
        # Dev mode without a key — log and move on
        return None

    tpl_def = TEMPLATES.get(n.template, TEMPLATES["generic"])
    subject = _env.from_string(tpl_def["subject"]).render(**n.payload)
    html = _env.get_template(tpl_def["html"]).render(**n.payload)

    # Recipient email must be in payload["to"] (resolved by the caller)
    to = n.payload.get("to")
    if not to:
        raise ValueError(f"notification {n.id}: payload.to is required for email")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.email_from,
                "to": [to],
                "subject": subject,
                "html": html,
            },
        )
        resp.raise_for_status()
        return resp.json().get("id")
