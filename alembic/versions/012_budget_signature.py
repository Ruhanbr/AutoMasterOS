"""012 — Assinatura digital do orçamento

Revision ID: 012_budget_signature
Revises: 011_client_portal
Create Date: 2026-05-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "012_budget_signature"
down_revision = "011_client_portal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("service_orders", sa.Column("budget_signature", sa.Text, nullable=True))
    op.add_column("service_orders", sa.Column("budget_signer_name", sa.String(200), nullable=True))
    op.add_column("service_orders", sa.Column("budget_signer_document", sa.String(20), nullable=True))
    op.add_column("service_orders", sa.Column("budget_signer_ip", sa.String(45), nullable=True))


def downgrade() -> None:
    op.drop_column("service_orders", "budget_signature")
    op.drop_column("service_orders", "budget_signer_name")
    op.drop_column("service_orders", "budget_signer_document")
    op.drop_column("service_orders", "budget_signer_ip")
