"""Celery tasks — notifications, AI batches, scheduled checks.

Tasks are thin: they call a service function inside a fresh DB session.
"""

import asyncio
from uuid import UUID

from alpago.core.database import db_session
from alpago.core.logging import log, setup_logging
from alpago.workers.celery_app import celery_app


setup_logging()


def _run(coro):
    """Run an async coroutine from a sync Celery task body."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Should not happen in Celery worker, but be defensive
            return asyncio.ensure_future(coro)
    except RuntimeError:
        pass
    return asyncio.run(coro)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def send_notification(self, notification_id: str) -> None:
    """Deliver one notification via its channel."""
    async def _go() -> None:
        from datetime import datetime, timezone
        from alpago.models.notification import (
            Notification, NotificationChannel, NotificationStatus,
        )
        async with db_session() as session:
            n = await session.get(Notification, UUID(notification_id))
            if n is None:
                log.warning("notification.missing", id=notification_id)
                return
            try:
                if n.channel == NotificationChannel.email:
                    from alpago.integrations.email import send_email_notification
                    provider_id = await send_email_notification(n)
                elif n.channel == NotificationChannel.whatsapp:
                    from alpago.integrations.whatsapp import send_whatsapp_notification
                    provider_id = await send_whatsapp_notification(n)
                else:
                    provider_id = None
                n.status = NotificationStatus.sent
                n.provider_id = provider_id
                n.sent_at = datetime.now(tz=timezone.utc)
            except Exception as e:
                n.status = NotificationStatus.failed
                n.error = str(e)[:1000]
                log.error("notification.send_failed", id=notification_id, error=str(e))
                raise

    try:
        _run(_go())
    except Exception as exc:
        raise self.retry(exc=exc) from exc


@celery_app.task
def check_approval_slas() -> int:
    """Beat task: escalate any active approval step past its SLA."""
    async def _go() -> int:
        from alpago.domain.approvals import escalate_overdue
        from alpago.domain.approvals.service import DefaultStepResolver

        async with db_session() as session:
            return await escalate_overdue(session, DefaultStepResolver())
    n = _run(_go())
    log.info("approval.sla_check", escalated=n)
    return n


@celery_app.task
def check_document_expiries() -> int:
    """Beat task: find documents expiring in 60/30/7 days and notify HR + PRO.
    Placeholder — Documents module is Phase 2."""
    log.info("documents.expiry_check", status="placeholder")
    return 0


@celery_app.task
def screen_cv_async(cv_id: str) -> None:
    """Fired on CV upload. Runs screen_cv() and persists the result.

    The sync path (`POST /candidates/{id}/screen`) also exists for UI-driven re-runs;
    this task is for async "run it in the background on upload" convenience.
    """
    async def _go() -> None:
        from alpago.modules.candidates import Cv, screen_candidate
        async with db_session() as session:
            cv = await session.get(Cv, UUID(cv_id))
            if cv is None:
                log.warning("cv.missing", id=cv_id)
                return
            # Only auto-screen if the hiring request has a JD (otherwise skip silently)
            from alpago.modules.hiring import HiringRequest
            from alpago.modules.candidates import Candidate
            cand = await session.get(Candidate, cv.candidate_id)
            if cand is None:
                return
            hr = await session.get(HiringRequest, cand.hiring_request_id)
            if hr is None or not hr.jd_markdown:
                log.info("cv.screen_skipped_no_jd", cv_id=cv_id)
                return
            try:
                await screen_candidate(session, cand.id)
                log.info("cv.screen_complete", cv_id=cv_id)
            except Exception as e:
                log.warning("cv.screen_failed", cv_id=cv_id, error=str(e)[:300])
    try:
        _run(_go())
    except Exception as e:
        log.warning("cv.screen_task_failed", cv_id=cv_id, error=str(e)[:300])
