import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TenantMixin


class InvoiceStatus(str, Enum):
    PENDENTE = "PENDENTE"
    PROCESSANDO = "PROCESSANDO"
    AUTORIZADA = "AUTORIZADA"
    REJEITADA = "REJEITADA"
    ERRO = "ERRO"

    @property
    def is_terminal(self) -> bool:
        return self in {self.AUTORIZADA, self.REJEITADA}

    @property
    def is_retriable(self) -> bool:
        return self in {self.REJEITADA, self.ERRO}


class Invoice(TenantMixin, BaseModel):
    """
    NF-e vinculada a uma Ordem de Serviço.

    Controle de idempotência via idempotency_key (derivado do service_order_id).
    Nunca haverá duas NF-e para a mesma OS — garantido pelo unique constraint.
    """

    __tablename__ = "invoices"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    service_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_orders.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,  # CONSTRAINT: uma OS → uma NF-e máximo
        index=True,
    )

    # Chave de idempotência usada pelo worker para evitar duplicação em retries
    idempotency_key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )

    # Dados da nota fiscal
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    series: Mapped[str] = mapped_column(String(3), nullable=False, default="1")
    status: Mapped[InvoiceStatus] = mapped_column(
        String(20),
        nullable=False,
        default=InvoiceStatus.PENDENTE,
        index=True,
    )

    # Chave de acesso da NF-e (44 dígitos)
    access_key: Mapped[str | None] = mapped_column(String(44), unique=True, nullable=True)
    protocol_number: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Conteúdo gerado
    xml_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    xml_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    danfe_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Timestamps do ciclo de vida
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    authorized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Rejeição / erro
    rejection_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rejection_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Valores tributários calculados (JSON)
    tax_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Controle de retry
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Totais para auditoria rápida
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    total_tax: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )

    # Relationships
    service_order: Mapped["ServiceOrder"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ServiceOrder", back_populates="invoice", lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Invoice number={self.number} status={self.status!r} "
            f"key={self.idempotency_key!r}>"
        )
