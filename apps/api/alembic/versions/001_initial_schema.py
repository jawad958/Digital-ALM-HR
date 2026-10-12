"""initial schema — users, roles, departments, approvals, notifications, audit log

Revision ID: 001
Revises:
Create Date: 2026-10-10 10:00:00

Dialect-neutral: runs on SQLite (local dev) and PostgreSQL (Render) using
SQLAlchemy's generic Uuid + JSON + non-native Enum types.

Seeds the ten canonical roles and the five standard approval chain templates so
the engine works the moment the DB is up.
"""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

from alpago.domain.approvals.service import STANDARD_CHAINS
from alpago.models.role import ROLE_KEYS

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


# Enum string values — stored as plain VARCHAR (native_enum=False in models).
USER_STATUSES = ("active", "invited", "suspended")
AUTH_PROVIDERS = ("google", "microsoft", "magic_link")
APPROVAL_REQ_STATUSES = (
    "draft", "pending", "in_review", "approved", "rejected", "changes_requested", "cancelled",
)
APPROVAL_STEP_STATUSES = (
    "pending", "active", "approved", "rejected", "changes_requested",
    "skipped", "delegated", "escalated",
)
NOTIF_CHANNELS = ("in_app", "email", "whatsapp")
NOTIF_STATUSES = ("pending", "sent", "failed", "delivered", "read")


def upgrade() -> None:
    # ── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("name", sa.String(200)),
        sa.Column("status", sa.Enum(*USER_STATUSES, native_enum=False, length=20),
                  nullable=False, server_default="active"),
        sa.Column("auth_provider", sa.Enum(*AUTH_PROVIDERS, native_enum=False, length=20)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ── roles ────────────────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("permissions", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "user_roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_key", sa.String(100)),
        sa.Column("scope", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.UniqueConstraint("user_id", "role_id", "scope_key", name="uq_user_role_scope"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])

    # ── departments ──────────────────────────────────────────────────────────
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("key", sa.String(60), nullable=False, unique=True),
        sa.Column("parent_id", sa.Uuid(), sa.ForeignKey("departments.id")),
        sa.Column("head_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
    )
    op.create_index("ix_departments_name", "departments", ["name"])

    # ── approval_chain_templates ─────────────────────────────────────────────
    op.create_table(
        "approval_chain_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_type", sa.String(60), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("steps", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.UniqueConstraint("request_type", "active", name="uq_chain_type_active"),
    )
    op.create_index("ix_approval_chain_templates_request_type", "approval_chain_templates", ["request_type"])

    # ── approval_requests ────────────────────────────────────────────────────
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_type", sa.String(60), nullable=False),
        sa.Column("subject_type", sa.String(60), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("chain_template_id", sa.Uuid(),
                  sa.ForeignKey("approval_chain_templates.id"), nullable=False),
        sa.Column("submitter_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.Enum(*APPROVAL_REQ_STATUSES, native_enum=False, length=20),
                  nullable=False, server_default="pending"),
        sa.Column("current_step_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("context", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
    )
    op.create_index("ix_approval_requests_request_type", "approval_requests", ["request_type"])
    op.create_index("ix_approval_requests_subject_id", "approval_requests", ["subject_id"])
    op.create_index("ix_approval_requests_submitter_user_id", "approval_requests", ["submitter_user_id"])
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])

    # ── approval_steps ───────────────────────────────────────────────────────
    op.create_table(
        "approval_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("approval_request_id", sa.Uuid(),
                  sa.ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_index", sa.Integer, nullable=False),
        sa.Column("approver_role", sa.String(40), nullable=False),
        sa.Column("approver_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("scope", sa.String(40), nullable=False, server_default="global"),
        sa.Column("sla_hours", sa.Integer, nullable=False, server_default="48"),
        sa.Column("status", sa.Enum(*APPROVAL_STEP_STATUSES, native_enum=False, length=20),
                  nullable=False, server_default="pending"),
        sa.Column("comment", sa.String(2000)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("delegated_to_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.UniqueConstraint("approval_request_id", "step_index", name="uq_step_order"),
    )
    op.create_index("ix_approval_steps_approval_request_id", "approval_steps", ["approval_request_id"])

    # ── notifications ────────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.Enum(*NOTIF_CHANNELS, native_enum=False, length=20), nullable=False),
        sa.Column("template", sa.String(60), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("status", sa.Enum(*NOTIF_STATUSES, native_enum=False, length=20),
                  nullable=False, server_default="pending"),
        sa.Column("provider_id", sa.String(200)),
        sa.Column("error", sa.String(1000)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_status", "notifications", ["status"])

    # ── audit_logs ───────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("subject_type", sa.String(60), nullable=False),
        sa.Column("subject_id", sa.Uuid()),
        sa.Column("before", sa.JSON),
        sa.Column("after", sa.JSON),
        sa.Column("context", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_subject_type", "audit_logs", ["subject_type"])
    op.create_index("ix_audit_logs_subject_id", "audit_logs", ["subject_id"])

    # ── seed roles ───────────────────────────────────────────────────────────
    roles_t = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("key", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
    )
    role_defs = [
        ("admin", "Administrator", "Full platform access"),
        ("hr_lead", "HR Lead", "Read all employee data; configure templates"),
        ("ta", "Talent Acquisition", "Manage candidates & interviews"),
        ("pro", "PRO Officer", "Visa & document management"),
        ("initiating_manager", "Initiating Manager", "Create hiring requests for own department"),
        ("agm", "AGM", "First-tier approvals"),
        ("gm", "GM", "Second-tier approvals"),
        ("ceo", "CEO", "Final approvals"),
        ("it", "IT", "Fulfil IT provisioning & asset tasks"),
        ("employee", "Employee", "Self-service for own profile & requests"),
    ]
    assert set(k for k, _, _ in role_defs) == ROLE_KEYS, "role_defs must match ROLE_KEYS"
    op.bulk_insert(
        roles_t,
        [{"id": uuid4(), "key": k, "name": n, "description": d} for k, n, d in role_defs],
    )

    # ── seed approval chain templates ────────────────────────────────────────
    chains_t = sa.table(
        "approval_chain_templates",
        sa.column("id", sa.Uuid()),
        sa.column("request_type", sa.String),
        sa.column("name", sa.String),
        sa.column("steps", sa.JSON),
        sa.column("active", sa.Boolean),
    )
    op.bulk_insert(
        chains_t,
        [
            {
                "id": uuid4(),
                "request_type": c["request_type"],
                "name": c["name"],
                "steps": c["steps"],
                "active": True,
            }
            for c in STANDARD_CHAINS
        ],
    )


def downgrade() -> None:
    for t in [
        "audit_logs", "notifications", "approval_steps", "approval_requests",
        "approval_chain_templates", "departments", "user_roles", "roles", "users",
    ]:
        op.drop_table(t)
