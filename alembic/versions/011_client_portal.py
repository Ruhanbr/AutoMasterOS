"""011 — Portal do Cliente: public_token + campos de orçamento

Revision ID: 011_client_portal
Revises: 010_tenant_logo
Create Date: 2026-05-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "011_client_portal"
down_revision = "010_tenant_logo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Token público único por OS (UUID string)
    op.add_column(
        "service_orders",
        sa.Column("public_token", sa.String(36), nullable=True),
    )
    # Preenche token para OS existentes
    op.execute(
        "UPDATE service_orders SET public_token = gen_random_uuid()::text WHERE public_token IS NULL"
    )
    # Torna obrigatório e único
    op.alter_column("service_orders", "public_token", nullable=False)
    op.create_unique_constraint("uq_service_orders_public_token", "service_orders", ["public_token"])
    op.create_index("ix_service_orders_public_token", "service_orders", ["public_token"])

    # Status do orçamento enviado ao cliente
    op.add_column(
        "service_orders",
        sa.Column("budget_status", sa.String(30), nullable=False, server_default="RASCUNHO"),
    )
    op.add_column(
        "service_orders",
        sa.Column("budget_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "service_orders",
        sa.Column("budget_approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "service_orders",
        sa.Column("budget_rejected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "service_orders",
        sa.Column("budget_rejection_reason", sa.Text, nullable=True),
    )
    op.add_column(
        "service_orders",
        sa.Column("client_viewed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_index("ix_service_orders_public_token", "service_orders")
    op.drop_constraint("uq_service_orders_public_token", "service_orders")
    op.drop_column("service_orders", "public_token")
    op.drop_column("service_orders", "budget_status")
    op.drop_column("service_orders", "budget_sent_at")
    op.drop_column("service_orders", "budget_approved_at")
    op.drop_column("service_orders", "budget_rejected_at")
    op.drop_column("service_orders", "budget_rejection_reason")
    op.drop_column("service_orders", "client_viewed_at")
