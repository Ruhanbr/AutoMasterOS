"""Add fazenda to clients, chassis_number to machines

Revision ID: 007_fazenda_chassis
Revises: 006_machine_client_isolation
Create Date: 2026-05-05 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_fazenda_chassis"
down_revision: Union[str, None] = "006_machine_client_isolation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Campo "nome da fazenda / propriedade" no cadastro do cliente (opcional)
    op.add_column(
        "clients",
        sa.Column("fazenda", sa.String(200), nullable=True),
    )

    # Campo chassi na máquina (opcional)
    op.add_column(
        "machines",
        sa.Column("chassis_number", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("machines", "chassis_number")
    op.drop_column("clients", "fazenda")
