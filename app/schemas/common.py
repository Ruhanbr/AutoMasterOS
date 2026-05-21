import re
import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, field_validator

T = TypeVar("T")


class AutoMasterBaseModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        str_strip_whitespace=True,
    )


class TimestampSchema(AutoMasterBaseModel):
    created_at: datetime
    updated_at: datetime


class UUIDSchema(AutoMasterBaseModel):
    id: uuid.UUID


class PaginatedResponse(AutoMasterBaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> "PaginatedResponse[T]":
        pages = max(1, -(-total // page_size))
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


class MessageResponse(AutoMasterBaseModel):
    message: str
    detail: dict[str, Any] | None = None


def validate_cpf(cpf: str) -> str:
    digits = re.sub(r"\D", "", cpf)
    if len(digits) != 11:
        raise ValueError("CPF deve ter 11 dígitos")
    if len(set(digits)) == 1:
        raise ValueError("CPF inválido")
    return digits


def validate_cnpj(cnpj: str) -> str:
    digits = re.sub(r"\D", "", cnpj)
    if len(digits) != 14:
        raise ValueError("CNPJ deve ter 14 dígitos")
    return digits


def validate_cpf_or_cnpj(value: str) -> str:
    """Aceita CPF (11 dígitos) ou CNPJ (14 dígitos)."""
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11:
        return validate_cpf(digits)
    if len(digits) == 14:
        return digits
    raise ValueError("Documento deve ser CPF (11 dígitos) ou CNPJ (14 dígitos)")


def validate_document(document: str, document_type: str) -> str:
    if document_type == "CPF":
        return validate_cpf(document)
    return validate_cnpj(document)
