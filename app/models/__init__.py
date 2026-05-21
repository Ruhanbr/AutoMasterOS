"""
Importa todos os models para garantir que o metadata do SQLAlchemy
esteja populado antes de qualquer operação de migration ou criação de tabelas.
"""
from app.models.base import Base, BaseModel, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.tenant import Tenant
from app.models.client import Client, DocumentType
from app.models.machine import Machine
from app.models.service_order import (
    ItemType,
    ServiceOrder,
    ServiceOrderItem,
    ServiceOrderStatus,
)
from app.models.invoice import Invoice, InvoiceStatus
from app.models.user import User, UserRole
from app.models.password_reset_token import PasswordResetToken

__all__ = [
    "Base",
    "BaseModel",
    "TenantMixin",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "Tenant",
    "Client",
    "DocumentType",
    "Machine",
    "ServiceOrder",
    "ServiceOrderItem",
    "ServiceOrderStatus",
    "ItemType",
    "Invoice",
    "InvoiceStatus",
    "User",
    "UserRole",
    "PasswordResetToken",
]
