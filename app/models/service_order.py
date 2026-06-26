import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TenantMixin


class ServiceOrderStatus(str, Enum):
    ABERTA = "ABERTA"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    FINALIZADA = "FINALIZADA"
    CANCELADA = "CANCELADA"

    @classmethod
    def allowed_transitions(cls) -> dict["ServiceOrderStatus", set["ServiceOrderStatus"]]:
        return {
            cls.ABERTA: {cls.EM_ANDAMENTO, cls.CANCELADA},
            cls.EM_ANDAMENTO: {cls.FINALIZADA, cls.CANCELADA},
            cls.FINALIZADA: set(),
            cls.CANCELADA: set(),
        }

    def can_transition_to(self, target: "ServiceOrderStatus") -> bool:
        return target in self.allowed_transitions().get(self, set())


class BudgetStatus(str, Enum):
    """Status do orçamento enviado ao cliente para aprovação."""
    RASCUNHO = "RASCUNHO"                       # ainda não enviado
    AGUARDANDO_APROVACAO = "AGUARDANDO_APROVACAO"  # link enviado, aguardando resposta
    APROVADO = "APROVADO"                        # cliente aprovou
    RECUSADO = "RECUSADO"                        # cliente recusou


class ItemType(str, Enum):
    SERVICO = "SERVICO"
    PECA = "PECA"
    DESLOCAMENTO = "DESLOCAMENTO"


class ServiceOrder(TenantMixin, BaseModel):
    """Ordem de Serviço — entidade central da oficina."""

    __tablename__ = "service_orders"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    machine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("machines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[ServiceOrderStatus] = mapped_column(
        String(20),
        nullable=False,
        default=ServiceOrderStatus.ABERTA,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    solution: Mapped[str | None] = mapped_column(Text, nullable=True)
    technician_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    technician_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    technician_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expected_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    total_services: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    total_parts: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    total_displacement: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    total_discount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )

    # ── Portal do Cliente ─────────────────────────────────────────────────────
    # Token público único — usado na URL do portal sem autenticação
    public_token: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    budget_status: Mapped[BudgetStatus] = mapped_column(
        String(30),
        nullable=False,
        default=BudgetStatus.RASCUNHO,
    )
    budget_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    budget_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    budget_rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    budget_rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Assinatura digital
    budget_signature: Mapped[str | None] = mapped_column(Text, nullable=True)       # base64 PNG
    budget_signer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    budget_signer_document: Mapped[str | None] = mapped_column(String(20), nullable=True)
    budget_signer_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Relationships
    client: Mapped["Client"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Client", back_populates="service_orders", lazy="selectin"
    )
    machine: Mapped["Machine | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Machine", back_populates="service_orders", lazy="selectin"
    )
    items: Mapped[list["ServiceOrderItem"]] = relationship(
        "ServiceOrderItem",
        back_populates="service_order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    invoice: Mapped["Invoice | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Invoice",
        back_populates="service_order",
        uselist=False,
        lazy="selectin",
    )

    def recalculate_totals(self) -> None:
        self.total_services = sum(
            (i.total_price for i in self.items if i.item_type == ItemType.SERVICO),
            Decimal("0.00"),
        )
        self.total_parts = sum(
            (i.total_price for i in self.items if i.item_type == ItemType.PECA),
            Decimal("0.00"),
        )
        self.total_displacement = sum(
            (i.total_price for i in self.items if i.item_type == ItemType.DESLOCAMENTO),
            Decimal("0.00"),
        )
        gross = self.total_services + self.total_parts + self.total_displacement
        self.total_amount = gross - self.total_discount

    def __repr__(self) -> str:
        return f"<ServiceOrder number={self.number} status={self.status!r}>"


class ServiceOrderItem(BaseModel):
    """Item de uma OS — pode ser serviço ou peça."""

    __tablename__ = "service_order_items"

    service_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    stock_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    item_type: Mapped[ItemType] = mapped_column(
        String(20), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    ncm_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    part_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(10, 3), nullable=False, default=Decimal("1.000")
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    discount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    total_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )

    # Relationships
    service_order: Mapped[ServiceOrder] = relationship(
        "ServiceOrder", back_populates="items", lazy="selectin"
    )

    def compute_total(self) -> None:
        self.total_price = (self.quantity * self.unit_price) - self.discount

    def __repr__(self) -> str:
        return f"<ServiceOrderItem type={self.item_type!r} desc={self.description[:30]!r}>"
