import uuid
from pydantic import EmailStr, field_validator

from app.schemas.common import AutoMasterBaseModel, TimestampSchema, UUIDSchema, validate_cpf_or_cnpj


class TenantCreate(AutoMasterBaseModel):
    name: str
    document: str
    email: EmailStr
    phone: str | None = None
    razao_social: str
    nome_fantasia: str | None = None
    inscricao_estadual: str | None = None
    inscricao_municipal: str | None = None
    regime_tributario: int = 1
    crt: str = "1"
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    municipio: str | None = None
    uf: str | None = None
    cep: str | None = None
    codigo_municipio: str | None = None
    limite_tecnicos: int = 5

    @field_validator("document")
    @classmethod
    def validate_document(cls, v: str) -> str:
        return validate_cpf_or_cnpj(v)

    @field_validator("cep")
    @classmethod
    def normalize_cep(cls, v: str | None) -> str | None:
        if not v:  # trata None e string vazia ""
            return None
        digits = "".join(filter(str.isdigit, v))
        if len(digits) != 8:
            raise ValueError("CEP deve ter 8 dígitos")
        return digits


class TenantUpdate(AutoMasterBaseModel):
    name: str | None = None
    document: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    razao_social: str | None = None
    nome_fantasia: str | None = None
    inscricao_estadual: str | None = None
    inscricao_municipal: str | None = None
    regime_tributario: int | None = None
    crt: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    municipio: str | None = None
    uf: str | None = None
    cep: str | None = None
    limite_tecnicos: int | None = None

    @field_validator("document")
    @classmethod
    def validate_document(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_cpf_or_cnpj(v)

    @field_validator("cep")
    @classmethod
    def normalize_cep(cls, v: str | None) -> str | None:
        if not v:  # trata None e string vazia ""
            return None
        digits = "".join(filter(str.isdigit, v))
        if len(digits) != 8:
            raise ValueError("CEP deve ter 8 dígitos")
        return digits


class TenantSetupPayload(AutoMasterBaseModel):
    """Cria oficina + primeiro usuário ADMIN em uma única operação."""
    # Dados da oficina
    name: str
    document: str
    email: EmailStr
    phone: str | None = None
    razao_social: str
    nome_fantasia: str | None = None
    municipio: str | None = None
    uf: str | None = None
    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    bairro: str | None = None
    inscricao_estadual: str | None = None
    limite_tecnicos: int = 5
    regime_tributario: int = 1
    crt: str = "1"

    # Dados do administrador da oficina
    admin_nome: str
    admin_email: EmailStr

    @field_validator("document")
    @classmethod
    def validate_document(cls, v: str) -> str:
        return validate_cpf_or_cnpj(v)


class TenantSetupResponse(AutoMasterBaseModel):
    tenant: "TenantResponse"
    admin_email: str
    message: str

    model_config = {"from_attributes": True}


class TenantResponse(UUIDSchema, TimestampSchema):
    name: str
    document: str
    email: str
    phone: str | None
    razao_social: str
    nome_fantasia: str | None
    inscricao_estadual: str | None
    regime_tributario: int
    crt: str
    municipio: str | None
    uf: str | None
    active: bool
    limite_tecnicos: int
    logo_url: str | None = None
    pix_key: str | None = None
    pix_key_type: str | None = None


class PixKeyUpdate(AutoMasterBaseModel):
    """Payload para salvar/atualizar a chave PIX da oficina."""
    pix_key: str | None = None
    pix_key_type: str | None = None  # CPF, CNPJ, EMAIL, TELEFONE, EVP
