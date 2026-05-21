import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import field_validator, model_validator

from app.models.service_order import BudgetStatus, ItemType, ServiceOrderStatus
from app.schemas.client import ClientSummary
from app.schemas.common import AutoMasterBaseModel, TimestampSchema, UUIDSchema
from app.schemas.machine import MachineSummary


class ServiceOrderItemCreate(AutoMasterBaseModel):
    item_type: ItemType
    description: str
    ncm_code: str | None = None
    part_number: str | None = None
    quantity: Decimal = Decimal("1.000")
    unit_price: Decimal
    discount: Decimal = Decimal("0.00")

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Quantidade deve ser positiva")
        return v

    @field_validator("unit_price")
    @classmethod
    def validate_price(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Preço não pode ser negativo")
        return v

    @field_validator("ncm_code")
    @classmethod
    def validate_ncm(cls, v: str | None) -> str | None:
        if v is not None:
            digits = "".join(filter(str.isdigit, v))
            if len(digits) not in {6, 8}:
                raise ValueError("NCM deve ter 6 ou 8 dígitos")
            return digits
        return v


class ServiceOrderItemResponse(UUIDSchema, TimestampSchema):
    service_order_id: uuid.UUID
    item_type: ItemType
    description: str
    ncm_code: str | None
    part_number: str | None
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal
    total_price: Decimal


class ServiceOrderCreate(AutoMasterBaseModel):
    client_id: uuid.UUID
    machine_id: uuid.UUID | None = None
    description: str | None = None
    technician_name: str | None = None
    expected_delivery_at: datetime | None = None
    items: list[ServiceOrderItemCreate] = []


class ServiceOrderUpdate(AutoMasterBaseModel):
    description: str | None = None
    diagnosis: str | None = None
    solution: str | None = None
    technician_notes: str | None = None
    technician_name: str | None = None
    expected_delivery_at: datetime | None = None
    items: list[ServiceOrderItemCreate] | None = None


class ServiceOrderStatusUpdate(AutoMasterBaseModel):
    status: ServiceOrderStatus
    notes: str | None = None


class SendBudgetRequest(AutoMasterBaseModel):
    """Enviado quando o técnico quer mandar o orçamento para aprovação do cliente."""
    message: str | None = None  # mensagem opcional para incluir no portal


class BudgetDecisionRequest(AutoMasterBaseModel):
    """Enviado pelo cliente ao aprovar ou recusar o orçamento."""
    reason: str | None = None           # obrigatório apenas na recusa
    # Campos de assinatura digital (apenas na aprovação)
    signer_name: str | None = None      # nome completo do assinante
    signer_document: str | None = None  # CPF/CNPJ (opcional)
    signature: str | None = None        # base64 PNG do canvas


class ServiceOrderResponse(UUIDSchema, TimestampSchema):
    tenant_id: uuid.UUID
    client_id: uuid.UUID
    machine_id: uuid.UUID | None
    number: int
    status: ServiceOrderStatus
    description: str | None
    diagnosis: str | None
    solution: str | None
    technician_notes: str | None
    technician_name: str | None
    opened_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    expected_delivery_at: datetime | None
    total_services: Decimal
    total_parts: Decimal
    total_displacement: Decimal
    total_discount: Decimal
    total_amount: Decimal
    version: int
    items: list[ServiceOrderItemResponse]
    client: ClientSummary | None = None
    machine: MachineSummary | None = None
    # Portal do cliente
    public_token: str | None = None
    budget_status: BudgetStatus = BudgetStatus.RASCUNHO
    budget_sent_at: datetime | None = None
    budget_approved_at: datetime | None = None
    budget_rejected_at: datetime | None = None
    budget_rejection_reason: str | None = None
    client_viewed_at: datetime | None = None


# ── Resposta pública (sem dados sensíveis do tenant) ──────────────────────────

class PublicServiceOrderResponse(AutoMasterBaseModel):
    """Dados da OS para o portal do cliente — sem autenticação."""
    number: int
    status: ServiceOrderStatus
    budget_status: BudgetStatus
    description: str | None
    diagnosis: str | None
    technician_name: str | None
    opened_at: datetime
    expected_delivery_at: datetime | None
    budget_sent_at: datetime | None
    budget_approved_at: datetime | None
    budget_rejected_at: datetime | None
    budget_rejection_reason: str | None
    client_viewed_at: datetime | None
    total_services: Decimal
    total_parts: Decimal
    total_displacement: Decimal
    total_discount: Decimal
    total_amount: Decimal
    items: list[ServiceOrderItemResponse]
    # Dados do cliente/máquina (somente campos não sensíveis)
    client_name: str | None = None
    machine_info: str | None = None   # ex: "John Deere 6110J 2020"
    # Dados da oficina (para exibir no portal)
    workshop_name: str | None = None
    workshop_phone: str | None = None
    # Assinatura digital
    budget_signature: str | None = None
    budget_signer_name: str | None = None
    budget_signer_document: str | None = None


class ServiceOrderSummary(UUIDSchema, TimestampSchema):
    number: int
    status: ServiceOrderStatus
    budget_status: BudgetStatus = BudgetStatus.RASCUNHO
    total_amount: Decimal
    opened_at: datetime
    finished_at: datetime | None
    technician_name: str | None = None
    client: ClientSummary | None = None
