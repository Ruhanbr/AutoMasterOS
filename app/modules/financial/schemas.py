import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.financial.models import EntryType


class FinancialEntryCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entry_type: EntryType = EntryType.DESPESA
    amount: Decimal = Field(..., gt=0)
    description: str = Field(..., max_length=500)
    category: Optional[str] = Field(None, max_length=100)
    reference_date: datetime
    notes: Optional[str] = None
    service_order_id: Optional[uuid.UUID] = None


class FinancialExpenseCreate(BaseModel):
    """Schema for manual expense registration (always DESPESA)."""
    model_config = ConfigDict(from_attributes=True)

    amount: Decimal = Field(..., gt=0)
    description: str = Field(..., max_length=500)
    category: Optional[str] = Field(None, max_length=100)
    reference_date: datetime
    notes: Optional[str] = None


class FinancialEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    service_order_id: Optional[uuid.UUID]
    entry_type: EntryType
    amount: Decimal
    description: str
    category: Optional[str]
    reference_date: datetime
    idempotency_key: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class FinancialSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_receitas: Decimal
    total_despesas: Decimal
    saldo: Decimal
    date_from: Optional[datetime]
    date_to: Optional[datetime]


class FinancialEntryListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[FinancialEntryResponse]
    total: int
    page: int
    page_size: int
    pages: int
