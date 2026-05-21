import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.models.invoice import InvoiceStatus
from app.schemas.common import AutoMasterBaseModel, TimestampSchema, UUIDSchema


class InvoiceResponse(UUIDSchema, TimestampSchema):
    tenant_id: uuid.UUID
    service_order_id: uuid.UUID
    idempotency_key: str
    number: int | None
    series: str
    status: InvoiceStatus
    access_key: str | None
    protocol_number: str | None
    xml_path: str | None
    danfe_path: str | None
    issued_at: datetime | None
    authorized_at: datetime | None
    rejected_at: datetime | None
    rejection_code: str | None
    rejection_message: str | None
    tax_data: dict[str, Any] | None
    retry_count: int
    next_retry_at: datetime | None
    last_error: str | None
    total_amount: Decimal
    total_tax: Decimal


class InvoiceSummary(UUIDSchema):
    """Versão reduzida para exibição junto à OS."""

    status: InvoiceStatus
    number: int | None
    access_key: str | None
    authorized_at: datetime | None
    danfe_path: str | None


class TaxData(AutoMasterBaseModel):
    """Resultado do cálculo tributário para a NF-e."""

    regime: str
    base_calculo: Decimal
    aliquota_icms: Decimal
    valor_icms: Decimal
    aliquota_pis: Decimal
    valor_pis: Decimal
    aliquota_cofins: Decimal
    valor_cofins: Decimal
    valor_total_tributos: Decimal
    cst_icms: str
    csosn: str | None = None
