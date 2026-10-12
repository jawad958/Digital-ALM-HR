"""onboarding modules — hiring_requests, candidates, cvs, interviews, interview_evaluations, offers

Revision ID: 002
Revises: 001
Create Date: 2026-10-12 09:30:00
"""

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


HIRING_STATUSES = ("draft", "pending_approval", "approved", "rejected",
                   "sourcing", "filled", "closed", "cancelled")
CANDIDATE_STAGES = ("sourced", "screened", "shortlisted", "interviewing",
                    "offer", "hired", "rejected", "withdrawn")
INTERVIEW_STATUSES = ("scheduled", "completed", "cancelled", "no_show")
INTERVIEW_MODES = ("in_person", "video", "phone")
OFFER_STATUSES = ("draft", "pending_approval", "approved", "rejected_internally",
                  "sent", "accepted", "declined", "withdrawn", "expired")


def _ts_cols():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    ]


def _audit_cols():
    return [
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id")),
    ]


def upgrade() -> None:
    # ── hiring_requests ──
    op.create_table(
        "hiring_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("role_title", sa.String(200), nullable=False),
        sa.Column("department", sa.String(100), nullable=False),
        sa.Column("department_id", sa.Uuid()),
        sa.Column("seniority", sa.String(40), nullable=False, server_default="mid"),
        sa.Column("positions", sa.Integer, nullable=False, server_default="1"),
        sa.Column("salary_min", sa.Integer),
        sa.Column("salary_max", sa.Integer),
        sa.Column("currency", sa.String(10), nullable=False, server_default="AED"),
        sa.Column("justification", sa.String(2000)),
        sa.Column("target_start_date", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Enum(*HIRING_STATUSES, native_enum=False, length=30),
                  nullable=False, server_default="draft"),
        sa.Column("jd_markdown", sa.Text),
        sa.Column("jd_generated_by_ai", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("approval_request_id", sa.Uuid(), sa.ForeignKey("approval_requests.id")),
        sa.Column("extra", sa.JSON, nullable=False, server_default="{}"),
        *_ts_cols(), *_audit_cols(),
    )
    op.create_index("ix_hiring_requests_status", "hiring_requests", ["status"])

    # ── candidates ──
    op.create_table(
        "candidates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("hiring_request_id", sa.Uuid(), sa.ForeignKey("hiring_requests.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("phone", sa.String(40)),
        sa.Column("source", sa.String(40)),
        sa.Column("stage", sa.Enum(*CANDIDATE_STAGES, native_enum=False, length=20),
                  nullable=False, server_default="sourced"),
        sa.Column("current_role", sa.String(200)),
        sa.Column("years_experience", sa.Integer),
        sa.Column("expected_salary", sa.Integer),
        sa.Column("notes", sa.String(2000)),
        *_ts_cols(), *_audit_cols(),
    )
    op.create_index("ix_candidates_hiring_request_id", "candidates", ["hiring_request_id"])
    op.create_index("ix_candidates_email", "candidates", ["email"])
    op.create_index("ix_candidates_stage", "candidates", ["stage"])

    # ── cvs ──
    op.create_table(
        "cvs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(),
                  sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("parsed_text", sa.Text),
        sa.Column("ai_score", sa.JSON),
        *_ts_cols(),
    )
    op.create_index("ix_cvs_candidate_id", "cvs", ["candidate_id"])

    # ── interviews ──
    op.create_table(
        "interviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("hiring_request_id", sa.Uuid(), sa.ForeignKey("hiring_requests.id"), nullable=False),
        sa.Column("round_name", sa.String(80), nullable=False, server_default="Round 1"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=False, server_default="60"),
        sa.Column("mode", sa.Enum(*INTERVIEW_MODES, native_enum=False, length=20),
                  nullable=False, server_default="video"),
        sa.Column("location_or_link", sa.String(500)),
        sa.Column("interviewer_user_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("status", sa.Enum(*INTERVIEW_STATUSES, native_enum=False, length=20),
                  nullable=False, server_default="scheduled"),
        sa.Column("questions", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("questions_generated_by_ai", sa.Boolean, nullable=False, server_default=sa.false()),
        *_ts_cols(), *_audit_cols(),
    )
    op.create_index("ix_interviews_candidate_id", "interviews", ["candidate_id"])
    op.create_index("ix_interviews_hiring_request_id", "interviews", ["hiring_request_id"])
    op.create_index("ix_interviews_status", "interviews", ["status"])

    # ── interview_evaluations ──
    op.create_table(
        "interview_evaluations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("interview_id", sa.Uuid(),
                  sa.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interviewer_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scores", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("overall_score", sa.Integer, nullable=False),
        sa.Column("verdict", sa.String(40), nullable=False),
        sa.Column("notes", sa.String(4000)),
        *_ts_cols(), *_audit_cols(),
    )
    op.create_index("ix_interview_evaluations_interview_id", "interview_evaluations", ["interview_id"])

    # ── offers ──
    op.create_table(
        "offers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("hiring_request_id", sa.Uuid(), sa.ForeignKey("hiring_requests.id"), nullable=False),
        sa.Column("role_title", sa.String(200), nullable=False),
        sa.Column("base_salary", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="AED"),
        sa.Column("allowances", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("letter_markdown", sa.Text),
        sa.Column("status", sa.Enum(*OFFER_STATUSES, native_enum=False, length=30),
                  nullable=False, server_default="draft"),
        sa.Column("approval_request_id", sa.Uuid(), sa.ForeignKey("approval_requests.id")),
        sa.Column("acceptance_token", sa.String(80), unique=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        *_ts_cols(), *_audit_cols(),
    )
    op.create_index("ix_offers_candidate_id", "offers", ["candidate_id"])
    op.create_index("ix_offers_hiring_request_id", "offers", ["hiring_request_id"])
    op.create_index("ix_offers_status", "offers", ["status"])
    op.create_index("ix_offers_acceptance_token", "offers", ["acceptance_token"])


def downgrade() -> None:
    for t in ["offers", "interview_evaluations", "interviews", "cvs", "candidates", "hiring_requests"]:
        op.drop_table(t)
