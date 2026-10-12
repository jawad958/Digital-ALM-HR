"""Lazy status sync — call from get_* to reflect approval chain completion.

The approval engine stays decoupled from domain modules: it doesn't know what to
do with an approved request. This helper is the glue — called by hiring/offers
whenever they're read.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from alpago.models.approval import ApprovalRequest, ApprovalRequestStatus


async def sync_status_from_approval(
    session: AsyncSession,
    *,
    subject,
    pending_value,
    approved_value,
    rejected_value,
) -> None:
    """If subject's status is still 'pending' and its approval has resolved, flip it."""
    if subject.approval_request_id is None:
        return
    if subject.status != pending_value:
        return
    apr = await session.get(ApprovalRequest, subject.approval_request_id)
    if apr is None:
        return
    if apr.status == ApprovalRequestStatus.approved:
        subject.status = approved_value
        await session.flush()
    elif apr.status == ApprovalRequestStatus.rejected:
        subject.status = rejected_value
        await session.flush()
