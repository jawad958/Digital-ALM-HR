"""Allow a document record to exist before its scan is collected.

HR's employee register carries passport numbers, Emirates ID numbers and visa
expiry dates long before the scans are filed. Those records belong on the
expiry watchlist regardless, so file_path becomes nullable.

Revision ID: 007
Revises: 006
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.alter_column("file_path", existing_type=sa.String(length=600), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM documents WHERE file_path IS NULL")
    with op.batch_alter_table("documents") as batch:
        batch.alter_column("file_path", existing_type=sa.String(length=600), nullable=False)
