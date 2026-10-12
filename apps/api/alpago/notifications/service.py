"""Notification service — one entry point, three channels.

Flow:
  notify(user, template, payload)
    1. Resolve user's channel preferences (default: in_app + email + whatsapp)
    2. Write Notification rows (status=pending) — one per channel
    3. Enqueue Celery tasks to actually send
    4. Worker calls Resend / WhatsApp API / in-app stream, updates status

Services and routers call `notify()`. Workers call the integration modules directly.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from alpago.models.notification import Notification, NotificationChannel


DEFAULT_CHANNELS = (NotificationChannel.in_app, NotificationChannel.email, NotificationChannel.whatsapp)


async def notify(
    session: AsyncSession,
    *,
    user_id: UUID,
    template: str,
    payload: dict,
    channels: tuple[NotificationChannel, ...] = DEFAULT_CHANNELS,
) -> list[Notification]:
    """Queue one notification per channel. Returns the DB rows (status=pending)."""
    rows = [
        Notification(user_id=user_id, template=template, payload=payload, channel=ch)
        for ch in channels
    ]
    for r in rows:
        session.add(r)
    await session.flush()

    # Enqueue Celery send tasks — import locally to avoid import-time Redis dependency
    from alpago.workers.tasks import send_notification
    for r in rows:
        send_notification.delay(str(r.id))

    return rows


async def notify_many(
    session: AsyncSession,
    *,
    user_ids: list[UUID],
    template: str,
    payload: dict,
    channels: tuple[NotificationChannel, ...] = DEFAULT_CHANNELS,
) -> list[Notification]:
    out: list[Notification] = []
    for uid in user_ids:
        out.extend(await notify(session, user_id=uid, template=template, payload=payload, channels=channels))
    return out
