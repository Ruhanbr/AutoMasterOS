"""010_tenant_logo

Adds logo_url column to tenants table.

Revision ID: 010_tenant_logo
Revises: 009_auth_password_features
Create Date: 2026-05-08
"""

from alembic import op
import sqlalchemy as sa

revision = "010_tenant_logo"
down_revision = "009_auth_pwd_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("logo_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "logo_url")
