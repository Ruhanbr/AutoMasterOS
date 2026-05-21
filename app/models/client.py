import uuid
from enum import Enum

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TenantMixin


class DocumentType(str, Enum):
    CPF = "CPF"
    CNPJ = "CNPJ"


class Client(TenantMixin, BaseModel):
    """Cliente da oficina. Isolado por tenant_id."""

    __tablename__ = "clients"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    document: Mapped[str] = mapped_column(String(18), nullable=False, index=True)
    document_type: Mapped[DocumentType] = mapped_column(
        String(4), nullable=False, default=DocumentType.CPF
    )
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone_secondary: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Endereço completo
    logradouro: Mapped[str | None] = mapped_column(String(255), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(10), nullable=True)
    complemento: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(100), nullable=True)
    municipio: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(8), nullable=True)
    codigo_municipio: Mapped[str | None] = mapped_column(String(7), nullable=True)

    # Nome da fazenda / propriedade rural (opcional)
    fazenda: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Dados fiscais (PF/PJ)
    inscricao_estadual: Mapped[str | None] = mapped_column(String(20), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Tenant", back_populates="clients", lazy="selectin"
    )
    machines: Mapped[list["Machine"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Machine", back_populates="client", lazy="selectin"
    )
    service_orders: Mapped[list["ServiceOrder"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ServiceOrder", back_populates="client", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Client name={self.name!r} document={self.document!r}>"
