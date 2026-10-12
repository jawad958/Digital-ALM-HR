"""Celery app factory + beat schedule.

In LOCAL DEV (no REDIS_URL set) tasks run EAGERLY — synchronously in-process.
No Redis, no worker needed. `send_notification.delay(...)` just runs the task.

In PRODUCTION (REDIS_URL set) Celery works normally. Run with:
  celery -A alpago.workers.celery_app worker --loglevel=info
  celery -A alpago.workers.celery_app beat   --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab

from alpago.core.config import settings

broker = settings.redis_url or "memory://"
backend = settings.redis_url or "cache+memory://"

celery_app = Celery(
    "alpago",
    broker=broker,
    backend=backend,
    include=["alpago.workers.tasks"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=5 * 60,
    task_soft_time_limit=4 * 60,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    # Local dev: run tasks inline (no broker, no worker)
    task_always_eager=settings.celery_eager,
    task_eager_propagates=settings.celery_eager,
)

celery_app.conf.beat_schedule = {
    "check-approval-slas-every-hour": {
        "task": "alpago.workers.tasks.check_approval_slas",
        "schedule": crontab(minute=15),  # at :15 past every hour
    },
    "check-document-expiries-daily": {
        "task": "alpago.workers.tasks.check_document_expiries",
        "schedule": crontab(minute=0, hour=7),  # 07:00 UTC daily
    },
}
