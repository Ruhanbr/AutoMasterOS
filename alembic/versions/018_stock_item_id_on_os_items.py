"""018 add stock_item_id to service_order_items

Revision ID: 018
Revises: 017
Create Date: 2026-06-25

Links a service order item (type PECA) to a stock_items record so that
finalization can automatically reduce stock.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "service_order_items",
        sa.Column("stock_item_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_service_order_items_stock_item_id",
        "service_order_items",
        "stock_items",
        ["stock_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_service_order_items_stock_item_id",
        "service_order_items",
        ["stock_item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_service_order_items_stock_item_id", table_name="service_order_items")
    op.drop_constraint("fk_service_order_items_stock_item_id", "service_order_items", type_="foreignkey")
    op.drop_column("service_order_items", "stock_item_id")
