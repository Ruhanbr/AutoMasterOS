"""
Modelo de banco de dados para conexões John Deere por cliente.
Cada fazendeiro (cliente) autoriza o acesso às suas próprias máquinas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class DeereConnection(BaseModel):
    """Conexão OAuth entre um cliente AutoMaster e sua conta John Deere."""

    __tablename__ = "deere_connections"

    # Isolamento multi-tenant
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Cliente (fazendeiro) que autorizou o acesso
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Organização John Deere do cliente
    organization_id: Mapped[str] = mapped_column(String(100), nullable=False)
    organization_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    # Tokens OAuth
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<DeereConnection client={self.client_id} org={self.organization_id}>"
