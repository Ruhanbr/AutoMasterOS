import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class NotificationType(str, Enum):
    JD_ALERT = "JD_ALERT"           # Alerta/DTC John Deere gerou OS
    OS_ATRIBUIDA = "OS_ATRIBUIDA"   # OS atribuída ao técnico
    OS_CRIADA = "OS_CRIADA"         # OS criada manualmente (para gestor)
    GENERICO = "GENERICO"           # Avisos gerais


class Notification(BaseModel):
    """Notificação in-app por usuário."""

    __tablename__ = "notifications"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationship
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Notification type={self.type!r} user={self.user_id} read={self.read}>"
