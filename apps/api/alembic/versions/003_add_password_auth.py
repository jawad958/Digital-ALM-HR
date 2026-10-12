"""Add password_hash to users + seed admin.

Revision ID: 003_add_password_auth
Revises: 002_onboarding_modules
Create Date: 2026-10-12
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import bcrypt
import sqlalchemy as sa
from alembic import op


# revision identifiers
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


# Default admin seeded on first run. User can change the password via the API later.
SEED_EMAIL = "jawad@alpagomanufacturing.com"
SEED_NAME = "Jawad"
SEED_PASSWORD = "AlpagoDev2026!"


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("users")}

    # 1. Add the columns if they aren't there yet (idempotent — a prior run of
    #    this migration may have added them before erroring in the seed step).
    missing_pw = "password_hash" not in existing_cols
    missing_ll = "last_login_at" not in existing_cols
    if missing_pw or missing_ll:
        with op.batch_alter_table("users") as batch:
            if missing_pw:
                batch.add_column(sa.Column("password_hash", sa.String(length=255), nullable=True))
            if missing_ll:
                batch.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))

    # 2. Seed the admin user if the row doesn't already exist
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT id FROM users WHERE email = :email"),
        {"email": SEED_EMAIL},
    ).first()

    if existing is None:
        now = datetime.now(tz=timezone.utc).isoformat()
        conn.execute(
            sa.text(
                "INSERT INTO users "
                "(id, email, name, status, auth_provider, password_hash, created_at, updated_at) "
                "VALUES (:id, :email, :name, :status, :auth_provider, :password_hash, :created_at, :updated_at)"
            ),
            {
                "id": str(uuid4()),
                "email": SEED_EMAIL,
                "name": SEED_NAME,
                "status": "active",
                "auth_provider": "password",
                "password_hash": _hash(SEED_PASSWORD),
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("last_login_at")
        batch.drop_column("password_hash")
