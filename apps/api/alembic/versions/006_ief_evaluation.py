"""Interview Evaluation Form (IEF 1.2) fields + candidate visa/availability.

Revision ID: 006
Revises: 005
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


EVAL_COLUMNS = [
    ("relevant_industry_experience", sa.Boolean()),
    ("uae_work_experience", sa.Boolean()),
    ("strengths", sa.String(length=4000)),
    ("areas_for_improvement", sa.String(length=4000)),
    ("additional_comments", sa.String(length=4000)),
    ("hr_notes", sa.String(length=4000)),
]

CANDIDATE_COLUMNS = [
    ("visa_status", sa.String(length=60)),
    ("joining_availability", sa.String(length=120)),
]


def _add_missing(table: str, columns: list[tuple[str, object]]) -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {c["name"] for c in inspector.get_columns(table)}
    todo = [(n, t) for n, t in columns if n not in existing]
    if todo:
        with op.batch_alter_table(table) as batch:
            for name, coltype in todo:
                batch.add_column(sa.Column(name, coltype, nullable=True))


def upgrade() -> None:
    _add_missing("interview_evaluations", EVAL_COLUMNS)
    _add_missing("candidates", CANDIDATE_COLUMNS)

    # overall_score becomes derived, so it may legitimately be unknown
    with op.batch_alter_table("interview_evaluations") as batch:
        batch.alter_column("overall_score", existing_type=sa.Integer(), nullable=True)

    # Old 1-5 numeric scores don't map onto the IEF agreement scale; the verdict
    # vocabulary changed too. Normalise the handful of legacy rows.
    op.execute(
        "UPDATE interview_evaluations SET verdict = 'recommend' "
        "WHERE verdict IN ('strong_hire', 'hire')"
    )
    op.execute(
        "UPDATE interview_evaluations SET verdict = 'not_recommend' "
        "WHERE verdict IN ('no_hire', 'strong_no_hire')"
    )


def downgrade() -> None:
    with op.batch_alter_table("candidates") as batch:
        for name, _ in reversed(CANDIDATE_COLUMNS):
            batch.drop_column(name)
    with op.batch_alter_table("interview_evaluations") as batch:
        for name, _ in reversed(EVAL_COLUMNS):
            batch.drop_column(name)
