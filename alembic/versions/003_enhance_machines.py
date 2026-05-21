"""enhance_machines

Revision ID: 003_enhance_machines
Revises: 002_add_stock_financial
Create Date: 2026-05-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_enhance_machines"
down_revision: Union[str, None] = "002_add_stock_financial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add deleted_at column
    op.add_column(
        "machines",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # 2. Add placa column
    op.add_column(
        "machines",
        sa.Column("placa", sa.String(length=20), nullable=True),
    )
    # 3. Add proprietario column
    op.add_column(
        "machines",
        sa.Column("proprietario", sa.String(length=200), nullable=True),
    )
    # 4. Add idempotency_key column
    op.add_column(
        "machines",
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
    )

    # 5. Drop existing global unique index on serial_number
    op.drop_index("ix_machines_serial_number", table_name="machines")

    # 6. Create per-tenant unique constraint on (tenant_id, serial_number)
    op.create_unique_constraint(
        "uq_machines_tenant_serial",
        "machines",
        ["tenant_id", "serial_number"],
    )

    # 7. Create partial unique index on (tenant_id, placa) WHERE placa IS NOT NULL
    op.create_index(
        "uq_machines_tenant_placa",
        "machines",
        ["tenant_id", "placa"],
        unique=True,
        postgresql_where=sa.text("placa IS NOT NULL"),
    )

    # 8. Create index on deleted_at
    op.create_index(
        "ix_machines_deleted_at",
        "machines",
        ["deleted_at"],
        unique=False,
    )

    # 9. Create unique index on idempotency_key WHERE NOT NULL
    op.create_index(
        "ix_machines_idempotency_key",
        "machines",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_machines_idempotency_key", table_name="machines")
    op.drop_index("ix_machines_deleted_at", table_name="machines")
    op.drop_index("uq_machines_tenant_placa", table_name="machines")
    op.drop_constraint("uq_machines_tenant_serial", "machines", type_="unique")

    # Re-create global unique index on serial_number
    op.create_index(
        "ix_machines_serial_number",
        "machines",
        ["serial_number"],
        unique=True,
    )

    op.drop_column("machines", "idempotency_key")
    op.drop_column("machines", "proprietario")
    op.drop_column("machines", "placa")
    op.drop_column("machines", "deleted_at")
