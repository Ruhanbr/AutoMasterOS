"""os_avancada — DESLOCAMENTO, version lock, índices compostos

Revision ID: 004_os_avancada
Revises: 003_enhance_machines
Create Date: 2026-05-01 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_os_avancada"
down_revision: Union[str, None] = "003_enhance_machines"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Expandir item_type VARCHAR(10 → 20) para caber "DESLOCAMENTO" (12 chars)
    op.alter_column(
        "service_order_items",
        "item_type",
        type_=sa.String(20),
        existing_type=sa.String(10),
        existing_nullable=False,
    )

    # 2. Subtotal de deslocamento na OS
    op.add_column(
        "service_orders",
        sa.Column(
            "total_displacement",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0.00",
        ),
    )

    # 3. Version lock para optimistic concurrency (complementa SELECT FOR UPDATE)
    op.add_column(
        "service_orders",
        sa.Column(
            "version",
            sa.Integer,
            nullable=False,
            server_default="1",
        ),
    )

    # 4. Índice composto: OS por máquina + tenant + status (N+1 free pagination)
    op.create_index(
        "ix_so_machine_tenant_status",
        "service_orders",
        ["machine_id", "tenant_id", "status"],
    )

    # 5. Índice composto: financeiro por tenant + status (receitas otimizado)
    op.create_index(
        "ix_so_tenant_status",
        "service_orders",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_so_tenant_status", table_name="service_orders")
    op.drop_index("ix_so_machine_tenant_status", table_name="service_orders")
    op.drop_column("service_orders", "version")
    op.drop_column("service_orders", "total_displacement")
    op.alter_column(
        "service_order_items",
        "item_type",
        type_=sa.String(10),
        existing_type=sa.String(20),
        existing_nullable=False,
    )
