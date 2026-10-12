"""SQLAlchemy models — one declarative Base.

Core models only. Domain modules (hiring, candidates, interviews, offers) define
their own models that inherit from Base; Alembic imports them explicitly in
alembic/env.py so autogenerate sees every table.

Keeping this file module-free avoids a circular import:
  modules.hiring  → api.deps  → models.__init__  → modules.hiring (!)
"""

from alpago.models.base import Base
from alpago.models.user import User
from alpago.models.role import Role, UserRole
from alpago.models.department import Department
from alpago.models.approval import (
    ApprovalChainTemplate,
    ApprovalRequest,
    ApprovalStep,
    ApprovalRequestStatus,
    ApprovalStepStatus,
)
from alpago.models.notification import Notification, NotificationChannel, NotificationStatus
from alpago.models.audit import AuditLog

__all__ = [
    "Base",
    "User",
    "Role",
    "UserRole",
    "Department",
    "ApprovalChainTemplate",
    "ApprovalRequest",
    "ApprovalStep",
    "ApprovalRequestStatus",
    "ApprovalStepStatus",
    "Notification",
    "NotificationChannel",
    "NotificationStatus",
    "AuditLog",
]
