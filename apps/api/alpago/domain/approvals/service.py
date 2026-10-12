"""Default role resolver + hiring-specific chain seed helpers.

The resolver maps `role + scope + context` → the user_id who should decide this
step. For MVP we use a simple strategy:

  - `scope == "self"`     → the submitter's manager (manager_id in context)
  - `scope == "department"` → the first user with that role scoped to context.department_id
  - `scope == "global"`   → the first user with that role, unscoped

Replaceable with an org-chart-aware resolver later.
"""

from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from alpago.domain.approvals.engine import StepResolver
from alpago.models.role import Role, UserRole


class DefaultStepResolver(StepResolver):
    async def resolve(
        self, *, role: str, scope: str, context: dict, session: AsyncSession
    ) -> UUID | None:
        if scope == "self":
            manager_id = context.get("manager_id")
            return UUID(manager_id) if manager_id else None

        role_row = (
            await session.execute(select(Role).where(Role.key == role))
        ).scalar_one_or_none()
        if role_row is None:
            return None

        stmt = select(UserRole).where(UserRole.role_id == role_row.id)
        if scope == "department" and (dept_id := context.get("department_id")):
            stmt = stmt.where(
                and_(
                    UserRole.scope_key == "department",
                    UserRole.scope["department_id"].astext == str(dept_id),
                )
            )
        else:
            # global: prefer unscoped role assignments
            stmt = stmt.where(UserRole.scope_key.is_(None))

        user_role = (await session.execute(stmt.limit(1))).scalar_one_or_none()
        return user_role.user_id if user_role else None


# Standard chain configs for Alpago request types — seeded in migration 001.
STANDARD_CHAINS: list[dict] = [
    {
        "request_type": "hiring_request",
        "name": "Hiring request (standard)",
        "steps": [
            {"role": "agm", "scope": "department", "sla_hours": 24},
            {"role": "gm", "scope": "global", "sla_hours": 48},
            {"role": "ceo", "scope": "global", "sla_hours": 72},
        ],
    },
    {
        "request_type": "offer",
        "name": "Offer letter approval",
        "steps": [
            {"role": "agm", "scope": "department", "sla_hours": 24},
            {"role": "gm", "scope": "global", "sla_hours": 24},
            {"role": "ceo", "scope": "global", "sla_hours": 48},
        ],
    },
    {
        "request_type": "leave_request",
        "name": "Leave request",
        "steps": [
            {"role": "initiating_manager", "scope": "self", "sla_hours": 24},
        ],
    },
    {
        "request_type": "comp_change",
        "name": "Compensation change",
        "steps": [
            {"role": "agm", "scope": "department", "sla_hours": 48},
            {"role": "gm", "scope": "global", "sla_hours": 72},
            {"role": "ceo", "scope": "global", "sla_hours": 72},
        ],
    },
    {
        "request_type": "asset_request",
        "name": "IT asset request",
        "steps": [
            {"role": "initiating_manager", "scope": "self", "sla_hours": 24},
            {"role": "it", "scope": "global", "sla_hours": 48},
        ],
    },
]
