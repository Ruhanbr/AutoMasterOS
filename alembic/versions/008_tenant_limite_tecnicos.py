"""Add limite_tecnicos to tenants

Revision ID: 008_tenant_limite_tecnico
Revises: 007_fazenda_chassis
Create Date: 2026-05-05 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_tenant_limite_tecnico"
down_revision: Union[str, None] = "007_fazenda_chassis"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "limite_tecnicos",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "limite_tecnicos")
