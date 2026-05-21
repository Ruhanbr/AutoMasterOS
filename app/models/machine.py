import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TenantMixin


class MachineType(str, Enum):
    TRATORES = "Tratores"
    COLHEITADEIRAS = "Colheitadeiras"
    PLANTADEIRAS = "Plantadeiras"
    SEMEADORAS = "Semeadoras"
    PULVERIZADORES = "Pulverizadores"
    OUTROS = "Outros"


class Machine(TenantMixin, BaseModel):
    """Máquina agrícola vinculada a um cliente."""

    __tablename__ = "machines"

    __table_args__ = (
        # Per-tenant serial uniqueness (replaces old global unique on serial_number)
        UniqueConstraint("tenant_id", "serial_number", name="uq_machines_tenant_serial"),
        # Partial unique index: (tenant_id, placa) WHERE placa IS NOT NULL
        Index(
            "uq_machines_tenant_placa",
            "tenant_id",
            "placa",
            unique=True,
            postgresql_where="placa IS NOT NULL",
        ),
    )

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

    machine_type: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(150), nullable=False)
    brand: Mapped[str] = mapped_column(String(100), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    engine_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    horsepower: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # New columns (003_enhance_machines migration)
    placa: Mapped[str | None] = mapped_column(String(20), nullable=True)
    chassis_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    proprietario: Mapped[str | None] = mapped_column(String(200), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)

    # Relationships
    client: Mapped["Client"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Client", back_populates="machines", lazy="selectin"
    )
    service_orders: Mapped[list["ServiceOrder"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ServiceOrder", back_populates="machine", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Machine brand={self.brand!r} model={self.model!r} serial={self.serial_number!r}>"
