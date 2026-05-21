"""Add auth password features

Revision ID: 009_auth_pwd_features
Revises: 008_tenant_limite_tecnico
Create Date: 2026-05-06 00:00:00.000000
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "009_auth_pwd_features"
down_revision: Union[str, None] = "008_tenant_limite_tecnico"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Campo para forçar troca de senha no próximo login
    op.add_column(
        "users",
        sa.Column(
            "precisa_trocar_senha",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    # 2. FK do técnico responsável na OS (nullable — não quebra dados existentes)
    op.add_column(
        "service_orders",
        sa.Column(
            "technician_user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_service_orders_technician_user",
        "service_orders",
        "users",
        ["technician_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_service_orders_technician_user_id",
        "service_orders",
        ["technician_user_id"],
    )

    # 3. Tabela de tokens de reset de senha
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("token", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_pwd_reset_tokens_user_expires",
        "password_reset_tokens",
        ["user_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_constraint("fk_service_orders_technician_user", "service_orders", type_="foreignkey")
    op.drop_index("ix_service_orders_technician_user_id", "service_orders")
    op.drop_column("service_orders", "technician_user_id")
    op.drop_column("users", "precisa_trocar_senha")
