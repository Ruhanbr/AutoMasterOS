import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.stock.models import MovementType


class StockItemCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku: str = Field(..., max_length=100)
    description: str = Field(..., max_length=500)
    ncm_code: Optional[str] = Field(None, max_length=8)
    unit: str = Field("UN", max_length=20)
    quantity: Decimal = Field(Decimal("0.000"), ge=0)
    min_quantity: Decimal = Field(Decimal("0.000"), ge=0)
    cost_price: Decimal = Field(Decimal("0.00"), ge=0)
    sale_price: Decimal = Field(Decimal("0.00"), ge=0)


class StockItemUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    description: Optional[str] = Field(None, max_length=500)
    ncm_code: Optional[str] = Field(None, max_length=8)
    unit: Optional[str] = Field(None, max_length=20)
    min_quantity: Optional[Decimal] = Field(None, ge=0)
    cost_price: Optional[Decimal] = Field(None, ge=0)
    sale_price: Optional[Decimal] = Field(None, ge=0)
    active: Optional[bool] = None


class StockItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    sku: str
    description: str
    ncm_code: Optional[str]
    unit: str
    quantity: Decimal
    min_quantity: Decimal
    cost_price: Decimal
    sale_price: Decimal
    active: bool
    deleted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class StockMovementCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    movement_type: MovementType
    quantity: Decimal = Field(..., gt=0)
    unit_cost: Decimal = Field(Decimal("0.00"), ge=0)
    reason: Optional[str] = None
    reference: Optional[str] = Field(None, max_length=100)
    service_order_id: Optional[uuid.UUID] = None


class StockMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    stock_item_id: uuid.UUID
    service_order_id: Optional[uuid.UUID]
    movement_type: MovementType
    quantity: Decimal
    quantity_before: Decimal
    quantity_after: Decimal
    unit_cost: Decimal
    reason: Optional[str]
    reference: Optional[str]
    created_at: datetime
    updated_at: datetime


class StockItemListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[StockItemResponse]
    total: int
    page: int
    page_size: int
    pages: int
