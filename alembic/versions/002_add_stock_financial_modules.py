"""add_stock_financial_modules

Revision ID: 002_add_stock_financial
Revises: e43a07aeceff
Create Date: 2026-05-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_add_stock_financial"
down_revision: Union[str, None] = "e43a07aeceff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── stock_items ───────────────────────────────────────────────────────────
    op.create_table(
        "stock_items",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("ncm_code", sa.String(length=8), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("min_quantity", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("cost_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("sale_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "sku", name="uq_stock_items_tenant_sku"),
    )
    op.create_index(op.f("ix_stock_items_tenant_id"), "stock_items", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_stock_items_sku"), "stock_items", ["sku"], unique=False)

    # ── stock_movements ───────────────────────────────────────────────────────
    op.create_table(
        "stock_movements",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("stock_item_id", sa.UUID(), nullable=False),
        sa.Column("service_order_id", sa.UUID(), nullable=True),
        sa.Column("movement_type", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("quantity_before", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("quantity_after", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stock_item_id"], ["stock_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stock_movements_tenant_id"), "stock_movements", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_stock_movements_stock_item_id"), "stock_movements", ["stock_item_id"], unique=False)
    op.create_index(op.f("ix_stock_movements_service_order_id"), "stock_movements", ["service_order_id"], unique=False)
    op.create_index(op.f("ix_stock_movements_movement_type"), "stock_movements", ["movement_type"], unique=False)

    # ── financial_entries ─────────────────────────────────────────────────────
    op.create_table(
        "financial_entries",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("service_order_id", sa.UUID(), nullable=True),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("reference_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(op.f("ix_financial_entries_tenant_id"), "financial_entries", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_financial_entries_service_order_id"), "financial_entries", ["service_order_id"], unique=False)
    op.create_index(op.f("ix_financial_entries_entry_type"), "financial_entries", ["entry_type"], unique=False)
    op.create_index(op.f("ix_financial_entries_idempotency_key"), "financial_entries", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_financial_entries_idempotency_key"), table_name="financial_entries")
    op.drop_index(op.f("ix_financial_entries_entry_type"), table_name="financial_entries")
    op.drop_index(op.f("ix_financial_entries_service_order_id"), table_name="financial_entries")
    op.drop_index(op.f("ix_financial_entries_tenant_id"), table_name="financial_entries")
    op.drop_table("financial_entries")

    op.drop_index(op.f("ix_stock_movements_movement_type"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_service_order_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_stock_item_id"), table_name="stock_movements")
    op.drop_index(op.f("ix_stock_movements_tenant_id"), table_name="stock_movements")
    op.drop_table("stock_movements")

    op.drop_index(op.f("ix_stock_items_sku"), table_name="stock_items")
    op.drop_index(op.f("ix_stock_items_tenant_id"), table_name="stock_items")
    op.drop_table("stock_items")
