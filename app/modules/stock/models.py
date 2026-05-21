import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class MovementType(str, Enum):
    ENTRADA = "ENTRADA"     # stock in
    SAIDA = "SAIDA"         # stock out
    AJUSTE = "AJUSTE"       # manual adjustment
    RESERVA = "RESERVA"     # reserved for OS
    BAIXA_OS = "BAIXA_OS"   # consumed by OS finalization


class StockItem(BaseModel):
    __tablename__ = "stock_items"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    ncm_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="UN")
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, default=Decimal("0.000")
    )
    min_quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, default=Decimal("0.000")
    )
    cost_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    sale_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    movements: Mapped[list["StockMovement"]] = relationship(
        "StockMovement", back_populates="stock_item", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_stock_items_tenant_sku"),
    )

    def __repr__(self) -> str:
        return f"<StockItem sku={self.sku!r} qty={self.quantity}>"


class StockMovement(BaseModel):
    __tablename__ = "stock_movements"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stock_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stock_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    service_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    movement_type: Mapped[MovementType] = mapped_column(
        String(20), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    quantity_before: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    quantity_after: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    stock_item: Mapped[StockItem] = relationship(
        "StockItem", back_populates="movements", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<StockMovement type={self.movement_type!r} qty={self.quantity}>"
