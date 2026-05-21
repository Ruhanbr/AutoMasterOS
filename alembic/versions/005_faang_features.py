"""FAANG features: assinatura_url, ix_os_machine_historico

Revision ID: 005_faang_features
Revises: 004_os_avancada
Create Date: 2026-05-02 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_faang_features"
down_revision: Union[str, None] = "004_os_avancada"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("assinatura_url", sa.String(500), nullable=True),
    )

    # Índice composto para histórico de OS por máquina (N+1 free, DESC)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_os_machine_historico
        ON service_orders (machine_id, tenant_id, created_at DESC)
        WHERE machine_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_os_machine_historico")
    op.drop_column("users", "assinatura_url")
