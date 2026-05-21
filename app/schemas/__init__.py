from app.schemas.common import (
    AutoMasterBaseModel,
    MessageResponse,
    PaginatedResponse,
    TimestampSchema,
    UUIDSchema,
)
from app.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate
from app.schemas.client import ClientCreate, ClientResponse, ClientSummary, ClientUpdate
from app.schemas.machine import MachineCreate, MachineResponse, MachineSummary, MachineUpdate
from app.schemas.service_order import (
    ServiceOrderCreate,
    ServiceOrderItemCreate,
    ServiceOrderItemResponse,
    ServiceOrderResponse,
    ServiceOrderStatusUpdate,
    ServiceOrderSummary,
    ServiceOrderUpdate,
)
from app.schemas.invoice import InvoiceResponse, InvoiceSummary, TaxData

__all__ = [
    "AutoMasterBaseModel",
    "MessageResponse",
    "PaginatedResponse",
    "TimestampSchema",
    "UUIDSchema",
    "TenantCreate",
    "TenantResponse",
    "TenantUpdate",
    "ClientCreate",
    "ClientResponse",
    "ClientSummary",
    "ClientUpdate",
    "MachineCreate",
    "MachineResponse",
    "MachineSummary",
    "MachineUpdate",
    "ServiceOrderCreate",
    "ServiceOrderItemCreate",
    "ServiceOrderItemResponse",
    "ServiceOrderResponse",
    "ServiceOrderStatusUpdate",
    "ServiceOrderSummary",
    "ServiceOrderUpdate",
    "InvoiceResponse",
    "InvoiceSummary",
    "TaxData",
]
