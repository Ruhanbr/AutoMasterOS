"""
Schemas de autenticação — request/response para os endpoints de auth.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Mínimo 8 caracteres")
    full_name: str = Field(min_length=1, max_length=200)
    role: UserRole = UserRole.TECNICO
    tenant_id: UUID


class UserResponse(BaseModel):
    id: UUID
    tenant_id: UUID | None = None
    email: str
    full_name: str
    role: UserRole
    active: bool
    created_at: datetime
    last_login_at: datetime | None = None
    assinatura_url: str | None = None

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_id: UUID | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos até expiração do access token
    force_password_change: bool = False  # ← NOVO


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, description="Mínimo 8 caracteres")


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, description="Mínimo 8 caracteres")


class PasswordChangeResponse(BaseModel):
    message: str
