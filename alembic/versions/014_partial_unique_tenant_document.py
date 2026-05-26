"""014_partial_unique_tenant_document

Substitui o índice único global em tenants.document por um índice único
PARCIAL (WHERE active = true), permitindo que o mesmo CNPJ seja reutilizado
após a desativação (soft-delete) de uma oficina.

Revision ID: 014
Revises: 013
Create Date: 2026-05-26
"""
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove o índice único global atual
    op.drop_index("ix_tenants_document", table_name="tenants")

    # Cria índice único parcial — só tenants ativos
    op.execute(
        "CREATE UNIQUE INDEX ix_tenants_document "
        "ON tenants (document) WHERE active = true"
    )


def downgrade() -> None:
    op.drop_index("ix_tenants_document", table_name="tenants")
    op.create_index("ix_tenants_document", "tenants", ["document"], unique=True)
