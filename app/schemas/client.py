import uuid

from pydantic import EmailStr, field_validator, model_validator

from app.models.client import DocumentType
from app.schemas.common import (
    AutoMasterBaseModel,
    TimestampSchema,
    UUIDSchema,
    validate_cnpj,
    validate_cpf,
)


class ClientCreate(AutoMasterBaseModel):
    name: str
    document: str
    document_type: DocumentType = DocumentType.CPF
    email: EmailStr | None = None
    phone: str | None = None
    phone_secondary: str | None = None
    fazenda: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    municipio: str | None = None
    uf: str | None = None
    cep: str | None = None
    codigo_municipio: str | None = None
    inscricao_estadual: str | None = None

    @model_validator(mode="after")
    def validate_document_by_type(self) -> "ClientCreate":
        if self.document_type == DocumentType.CPF:
            self.document = validate_cpf(self.document)
        else:
            self.document = validate_cnpj(self.document)
        return self

    @field_validator("cep")
    @classmethod
    def normalize_cep(cls, v: str | None) -> str | None:
        if v is None:
            return v
        digits = "".join(filter(str.isdigit, v))
        if len(digits) != 8:
            raise ValueError("CEP deve ter 8 dígitos")
        return digits

    @field_validator("uf")
    @classmethod
    def normalize_uf(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class ClientUpdate(AutoMasterBaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    phone_secondary: str | None = None
    fazenda: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    municipio: str | None = None
    uf: str | None = None
    cep: str | None = None
    codigo_municipio: str | None = None
    inscricao_estadual: str | None = None
    active: bool | None = None


class ClientResponse(UUIDSchema, TimestampSchema):
    tenant_id: uuid.UUID
    name: str
    document: str
    document_type: DocumentType
    email: str | None
    phone: str | None
    phone_secondary: str | None
    fazenda: str | None
    logradouro: str | None
    numero: str | None
    complemento: str | None
    bairro: str | None
    municipio: str | None
    uf: str | None
    cep: str | None
    codigo_municipio: str | None
    inscricao_estadual: str | None
    active: bool


class ClientSummary(UUIDSchema):
    """Versão reduzida para uso em listagens e relacionamentos."""

    name: str
    document: str
    document_type: DocumentType
    phone: str | None
    active: bool
