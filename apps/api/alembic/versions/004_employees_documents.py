"""Employees, onboarding tasks, and documents.

Revision ID: 004
Revises: 003
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("employee_code", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=True),
        sa.Column("offer_id", sa.Uuid(), nullable=True),
        # personal
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("personal_email", sa.String(length=320), nullable=True),
        sa.Column("work_email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("whatsapp", sa.String(length=40), nullable=True),
        sa.Column("nationality", sa.String(length=80), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(length=20), nullable=True),
        sa.Column("marital_status", sa.String(length=20), nullable=True),
        # job
        sa.Column("job_title", sa.String(length=200), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=False),
        sa.Column("division", sa.String(length=20), nullable=False, server_default="head_office"),
        sa.Column("reports_to_id", sa.Uuid(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("employment_type", sa.String(length=20), nullable=False, server_default="full_time"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="onboarding"),
        sa.Column("join_date", sa.Date(), nullable=True),
        sa.Column("probation_end_date", sa.Date(), nullable=True),
        sa.Column("contract_end_date", sa.Date(), nullable=True),
        sa.Column("exit_date", sa.Date(), nullable=True),
        # compensation
        sa.Column("base_salary", sa.Integer(), nullable=True),
        sa.Column("allowances", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="AED"),
        # compliance
        sa.Column("passport_number", sa.String(length=60), nullable=True),
        sa.Column("emirates_id", sa.String(length=60), nullable=True),
        sa.Column("visa_status", sa.String(length=60), nullable=True),
        # emergency contact
        sa.Column("emergency_name", sa.String(length=200), nullable=True),
        sa.Column("emergency_relation", sa.String(length=60), nullable=True),
        sa.Column("emergency_phone", sa.String(length=40), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=False, server_default="{}"),
        # mixins
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_employees_employee_code", "employees", ["employee_code"], unique=True)
    op.create_index("ix_employees_full_name", "employees", ["full_name"])
    op.create_index("ix_employees_department", "employees", ["department"])
    op.create_index("ix_employees_division", "employees", ["division"])
    op.create_index("ix_employees_status", "employees", ["status"])
    op.create_index("ix_employees_candidate_id", "employees", ["candidate_id"])
    op.create_index("ix_employees_offer_id", "employees", ["offer_id"])

    op.create_table(
        "onboarding_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("owner_role", sa.String(length=40), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_onboarding_tasks_employee_id", "onboarding_tasks", ["employee_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_type", sa.String(length=20), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("doc_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending_review"),
        sa.Column("filename", sa.String(length=300), nullable=False),
        sa.Column("file_path", sa.String(length=600), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("document_number", sa.String(length=120), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("issuing_country", sa.String(length=80), nullable=True),
        sa.Column("verified_by", sa.Uuid(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_documents_owner_type", "documents", ["owner_type"])
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    op.create_index("ix_documents_doc_type", "documents", ["doc_type"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_expiry_date", "documents", ["expiry_date"])


def downgrade() -> None:
    op.drop_table("documents")
    op.drop_table("onboarding_tasks")
    op.drop_table("employees")
