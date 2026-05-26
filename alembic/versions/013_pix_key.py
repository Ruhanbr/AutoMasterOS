"""013 — Chave PIX da oficina (tenant)

Revision ID: 013_pix_key
Revises: 012_budget_signature
Create Date: 2026-05-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "013_pix_key"
down_revision = "012_budget_signature"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("pix_key", sa.String(140), nullable=True))
    op.add_column("tenants", sa.Column("pix_key_type", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "pix_key")
    op.drop_column("tenants", "pix_key_type")
