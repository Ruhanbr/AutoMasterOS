"""Machine client isolation — composite index (client_id, tenant_id)

Revision ID: 006_machine_client_isolation
Revises: 005_faang_features
Create Date: 2026-05-02 00:00:00.000000

Objetivo:
  Suporta a query get_by_id_client_and_tenant com plan ótimo:
    WHERE id = ? AND client_id = ? AND tenant_id = ?
  O índice parcial exclui máquinas excluídas (deleted_at IS NULL)
  para manter o índice compacto.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "006_machine_client_isolation"
down_revision: Union[str, None] = "005_faang_features"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Índice composto para isolamento client_id + tenant_id em máquinas ativas
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_machines_client_tenant
        ON machines (client_id, tenant_id)
        WHERE deleted_at IS NULL
    """)

    # Índice para queries de listagem sem deleted_at
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_machines_tenant_active
        ON machines (tenant_id, active)
        WHERE deleted_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_machines_tenant_active")
    op.execute("DROP INDEX IF EXISTS ix_machines_client_tenant")
