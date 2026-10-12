"""Form submissions + the fields Alpago's Employee Information Form captures.

Revision ID: 005
Revises: 004
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


NEW_EMPLOYEE_COLUMNS = [
    ("uae_address", sa.String(length=500)),
    ("home_country_address", sa.String(length=500)),
    ("home_country_mobile", sa.String(length=40)),
    ("work_location", sa.String(length=200)),
    ("dependent_members", sa.Integer()),
    ("family_visa_status", sa.String(length=60)),
    ("bank_name", sa.String(length=200)),
    ("bank_account_number", sa.String(length=60)),
    ("iban", sa.String(length=60)),
    ("emergency_address", sa.String(length=500)),
    ("emergency_home_name", sa.String(length=200)),
    ("emergency_home_relation", sa.String(length=60)),
    ("emergency_home_phone", sa.String(length=40)),
    ("emergency_home_address", sa.String(length=500)),
]


def upgrade() -> None:
    op.create_table(
        "form_submissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("form_type", sa.String(length=60), nullable=False),
        sa.Column("form_code", sa.String(length=60), nullable=False),
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column("employee_name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=25), nullable=False, server_default="pending_approval"),
        sa.Column("data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("approval_request_id", sa.Uuid(), sa.ForeignKey("approval_requests.id"), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("acknowledged_by", sa.Uuid(), nullable=True),
        sa.Column("acknowledgement_note", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_form_submissions_form_type", "form_submissions", ["form_type"])
    op.create_index("ix_form_submissions_status", "form_submissions", ["status"])
    op.create_index("ix_form_submissions_employee_id", "form_submissions", ["employee_id"])
    op.create_index("ix_form_submissions_reference", "form_submissions", ["reference"], unique=True)

    # Employee Information Form (2024-Alpago/HR/EIF 4.1) fields
    inspector = sa.inspect(op.get_bind())
    existing = {c["name"] for c in inspector.get_columns("employees")}
    to_add = [(n, t) for n, t in NEW_EMPLOYEE_COLUMNS if n not in existing]
    if to_add:
        with op.batch_alter_table("employees") as batch:
            for name, coltype in to_add:
                batch.add_column(sa.Column(name, coltype, nullable=True))

    # Divisions were head_office/contracting; Alpago's forms say otherwise.
    op.execute("UPDATE employees SET division = 'manufacturing' WHERE division = 'head_office'")
    op.execute("UPDATE employees SET division = 'civil' WHERE division = 'contracting'")


def downgrade() -> None:
    with op.batch_alter_table("employees") as batch:
        for name, _ in reversed(NEW_EMPLOYEE_COLUMNS):
            batch.drop_column(name)
    op.drop_table("form_submissions")
