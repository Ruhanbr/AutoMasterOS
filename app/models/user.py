"""
Model de usuário — autenticação multi-tenant.

Cada usuário pertence a exatamente um tenant.
O mesmo email pode existir em tenants diferentes (constraint única por tenant+email).
"""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    TECNICO = "TECNICO"
    VIEWER = "VIEWER"
    SUPER_ADMIN = "SUPER_ADMIN"


class User(BaseModel):
    """Usuário autenticável de uma oficina (tenant)."""

    __tablename__ = "users"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        String(20), nullable=False, default=UserRole.TECNICO
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    assinatura_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    precisa_trocar_senha: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Tenant", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )

    def __repr__(self) -> str:
        return f"<User email={self.email!r} role={self.role!r}>"
