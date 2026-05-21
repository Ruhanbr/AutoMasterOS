from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TimestampMixin


class Tenant(BaseModel):
    """Representa uma oficina cadastrada na plataforma SaaS."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    document: Mapped[str] = mapped_column(String(18), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Dados fiscais da oficina (emitente da NF-e)
    razao_social: Mapped[str] = mapped_column(String(200), nullable=False)
    nome_fantasia: Mapped[str | None] = mapped_column(String(200), nullable=True)
    inscricao_estadual: Mapped[str | None] = mapped_column(String(20), nullable=True)
    inscricao_municipal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    regime_tributario: Mapped[int] = mapped_column(default=1, nullable=False)
    crt: Mapped[str] = mapped_column(String(1), default="1", nullable=False)

    # Endereço
    logradouro: Mapped[str | None] = mapped_column(String(255), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(10), nullable=True)
    complemento: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(100), nullable=True)
    municipio: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(8), nullable=True)
    codigo_municipio: Mapped[str | None] = mapped_column(String(7), nullable=True)

    # Logo da oficina (caminho ou URL público)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Limite de técnicos que podem ser cadastrados nesta oficina
    limite_tecnicos: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    clients: Mapped[list["Client"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Client", back_populates="tenant", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Tenant name={self.name!r} document={self.document!r}>"
