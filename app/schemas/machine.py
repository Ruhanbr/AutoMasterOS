import uuid
from datetime import datetime

from pydantic import field_validator

from app.models.machine import MachineType
from app.schemas.common import AutoMasterBaseModel, TimestampSchema, UUIDSchema
from app.schemas.client import ClientSummary


class MachineCreate(AutoMasterBaseModel):
    client_id: uuid.UUID
    machine_type: str
    model: str
    brand: str
    serial_number: str
    year: int | None = None
    color: str | None = None
    engine_number: str | None = None
    horsepower: str | None = None
    chassis_number: str | None = None
    notes: str | None = None
    placa: str | None = None
    proprietario: str | None = None

    @field_validator("year")
    @classmethod
    def validate_year(cls, v: int | None) -> int | None:
        if v is not None and not (1900 <= v <= 2100):
            raise ValueError("Ano inválido")
        return v

    @field_validator("serial_number")
    @classmethod
    def normalize_serial(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("machine_type")
    @classmethod
    def validate_machine_type(cls, v: str) -> str:
        valid_values = [mt.value for mt in MachineType]
        if v not in valid_values:
            raise ValueError(f"Tipo de máquina inválido. Valores aceitos: {valid_values}")
        return v

    @field_validator("placa")
    @classmethod
    def normalize_placa(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalized = v.strip().upper()
        if len(normalized) > 20:
            raise ValueError("Placa deve ter no máximo 20 caracteres")
        return normalized

    @field_validator("proprietario")
    @classmethod
    def normalize_proprietario(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        if len(stripped) > 200:
            raise ValueError("Proprietário deve ter no máximo 200 caracteres")
        return stripped


class MachineUpdate(AutoMasterBaseModel):
    machine_type: str | None = None
    model: str | None = None
    brand: str | None = None
    year: int | None = None
    color: str | None = None
    engine_number: str | None = None
    horsepower: str | None = None
    chassis_number: str | None = None
    notes: str | None = None
    active: bool | None = None
    placa: str | None = None
    proprietario: str | None = None

    @field_validator("placa")
    @classmethod
    def normalize_placa(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalized = v.strip().upper()
        if len(normalized) > 20:
            raise ValueError("Placa deve ter no máximo 20 caracteres")
        return normalized

    @field_validator("proprietario")
    @classmethod
    def normalize_proprietario(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        if len(stripped) > 200:
            raise ValueError("Proprietário deve ter no máximo 200 caracteres")
        return stripped


class MachineResponse(UUIDSchema, TimestampSchema):
    tenant_id: uuid.UUID
    client_id: uuid.UUID
    machine_type: str
    model: str
    brand: str
    serial_number: str
    year: int | None
    color: str | None
    engine_number: str | None
    horsepower: str | None
    chassis_number: str | None
    notes: str | None
    active: bool
    placa: str | None
    proprietario: str | None
    deleted_at: datetime | None
    client: ClientSummary | None = None


class MachineSummary(UUIDSchema):
    machine_type: str
    model: str
    brand: str
    serial_number: str
    year: int | None
