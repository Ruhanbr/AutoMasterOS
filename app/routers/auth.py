"""
Router de autenticação.

Rotas públicas (sem JWT):
  POST /auth/register  — cadastra novo usuário
  POST /auth/login     — autentica e retorna tokens
  POST /auth/refresh   — troca refresh token por novo par

Rota protegida:
  GET  /auth/me        — dados do usuário autenticado
"""

from fastapi import APIRouter, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.dependencies import CurrentUser, DbSession
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    PasswordChangeResponse,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.services.auth_service import AuthService

_limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar novo usuário",
)
async def register(data: UserCreate, session: DbSession) -> User:
    return await AuthService(session).register(data)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Autenticar e obter tokens",
)
async def login(data: LoginRequest, session: DbSession) -> TokenResponse:
    return await AuthService(session).login(data)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Renovar access token via refresh token",
)
async def refresh(data: RefreshRequest, session: DbSession) -> TokenResponse:
    return await AuthService(session).refresh(data.refresh_token)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Dados do usuário autenticado",
)
async def me(current_user: CurrentUser) -> User:
    return current_user


@router.post(
    "/forgot-password",
    response_model=PasswordChangeResponse,
    summary="Solicitar redefinição de senha por email",
)
@_limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    session: DbSession,
) -> PasswordChangeResponse:
    return await AuthService(session).forgot_password(data.email)


@router.post(
    "/reset-password",
    response_model=PasswordChangeResponse,
    summary="Redefinir senha via token de email",
)
async def reset_password(
    data: ResetPasswordRequest,
    session: DbSession,
) -> PasswordChangeResponse:
    return await AuthService(session).reset_password(data.token, data.new_password)


@router.post(
    "/change-password",
    response_model=PasswordChangeResponse,
    summary="Trocar senha (usuário autenticado)",
)
async def change_password(
    data: ChangePasswordRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> PasswordChangeResponse:
    return await AuthService(session).change_password(
        current_user, data.current_password, data.new_password
    )
