"""016_deere_per_client

Recria deere_connections com client_id (por cliente/fazendeiro)
em vez de apenas tenant_id.

Revision ID: 016
Revises: 015
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove tabela anterior (criada na 015, provavelmente vazia)
    op.drop_table("deere_connections")

    # Recria com client_id
    op.create_table(
        "deere_connections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column(
            "client_id", UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("organization_id", sa.String(100), nullable=False),
        sa.Column("organization_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("access_token", sa.Text, nullable=False),
        sa.Column("refresh_token", sa.Text, nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Garante uma conexão ativa por cliente
        sa.UniqueConstraint("client_id", "active", name="uq_deere_client_active"),
    )


def downgrade() -> None:
    op.drop_table("deere_connections")
