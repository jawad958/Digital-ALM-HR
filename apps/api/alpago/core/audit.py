"""Audit trail helper.

Every mutation in the system routes through `record_audit`. Reads are not
audited. Call it from service functions (not routers) so the trail is captured
regardless of which entry point triggered the change.

    await record_audit(
        session, actor=user, action="hiring_request.created",
        subject_type="hiring_request", subject_id=req.id,
        after={"role_title": req.role_title},
    )

Actions use dotted `noun.verb_past` form so they sort and filter sensibly.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from alpago.models.audit import AuditLog


def _jsonable(value: Any) -> Any:
    """Coerce a value into something the JSON column can store."""
    from datetime import date, datetime
    from decimal import Decimal
    from enum import Enum

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return str(value)


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    subject_type: str,
    subject_id: UUID | None = None,
    actor: Any | None = None,
    actor_user_id: UUID | None = None,
    before: dict | None = None,
    after: dict | None = None,
    context: dict | None = None,
) -> AuditLog:
    """Write one audit row. Never raises — auditing must not break the operation."""
    if actor_user_id is None and actor is not None:
        actor_user_id = getattr(actor, "id", None)

    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action[:80],
        subject_type=subject_type[:60],
        subject_id=subject_id,
        before=_jsonable(before) if before else None,
        after=_jsonable(after) if after else None,
        context=_jsonable(context or {}),
    )
    session.add(entry)
    await session.flush()
    return entry


def snapshot(obj: Any, fields: list[str]) -> dict:
    """Pick `fields` off a model instance into a JSON-safe dict.

    Handy for before/after pairs:
        before = snapshot(offer, ["status", "base_salary"])
        offer.status = OfferStatus.sent
        after = snapshot(offer, ["status", "base_salary"])
    """
    return {f: _jsonable(getattr(obj, f, None)) for f in fields}
