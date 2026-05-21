"""
AuthService — lógica de negócio para autenticação e gestão de usuários.

Fluxos:
  register  → valida tenant ativo + email único → cria User com senha hasheada
  login     → valida credenciais → atualiza last_login_at → retorna par de tokens
  refresh   → valida refresh token → emite novo par de tokens
"""

import uuid
from datetime import datetime, timezone

from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationException, BusinessRuleException, ResourceNotFoundException
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserRole
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate

logger = get_logger(__name__)


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._user_repo = UserRepository(session)
        self._tenant_repo = TenantRepository(session)

    # ── Registro ──────────────────────────────────────────────────────────────

    async def register(self, data: UserCreate) -> User:
        tenant = await self._tenant_repo.get_active_by_id(data.tenant_id)
        if tenant is None:
            raise ResourceNotFoundException("Tenant", str(data.tenant_id))

        existing = await self._user_repo.get_by_email_and_tenant(
            data.email, data.tenant_id
        )
        if existing is not None:
            raise BusinessRuleException(
                f"Email '{data.email}' já cadastrado neste tenant"
            )

        user = await self._user_repo.create(
            tenant_id=data.tenant_id,
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            role=data.role,
            active=True,
        )

        logger.info(
            "usuario_registrado",
            user_id=str(user.id),
            email=user.email,
            tenant_id=str(data.tenant_id),
        )
        return user

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login(self, data: LoginRequest) -> TokenResponse:
        # Login SUPER_ADMIN — não requer tenant_id
        if data.tenant_id is None:
            user = await self._user_repo.get_super_admin_by_email(data.email)
            if user is None or not verify_password(data.password, user.hashed_password):
                raise AuthenticationException("Email ou senha incorretos")
            if not user.active:
                raise AuthenticationException("Usuário inativo")
            user.last_login_at = datetime.now(timezone.utc)
            await self._user_repo.save(user)
            access_token = create_access_token(
                user_id=str(user.id),
                tenant_id=str(user.tenant_id),
                role=UserRole(user.role).value,
            )
            refresh_token = create_refresh_token(
                user_id=str(user.id),
                tenant_id=str(user.tenant_id),
            )
            logger.info("login_super_admin", user_id=str(user.id), email=user.email)
            return TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                force_password_change=user.precisa_trocar_senha,
            )

        user = await self._user_repo.get_by_email_and_tenant(
            data.email, data.tenant_id
        )

        if user is None or not verify_password(data.password, user.hashed_password):
            raise AuthenticationException("Email ou senha incorretos")

        if not user.active:
            raise AuthenticationException("Usuário inativo")

        user.last_login_at = datetime.now(timezone.utc)
        await self._user_repo.save(user)

        access_token = create_access_token(
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
            role=UserRole(user.role).value,
        )
        refresh_token = create_refresh_token(
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
        )

        logger.info("login_realizado", user_id=str(user.id), email=user.email)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            force_password_change=user.precisa_trocar_senha,
        )

    # ── Refresh ───────────────────────────────────────────────────────────────

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token)
        except JWTError:
            raise AuthenticationException("Refresh token inválido ou expirado")

        if payload.get("type") != "refresh":
            raise AuthenticationException("Token não é do tipo refresh")

        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationException("Token malformado")

        user = await self._user_repo.get_by_id(uuid.UUID(user_id))
        if user is None or not user.active:
            raise AuthenticationException("Usuário não encontrado ou inativo")

        access_token = create_access_token(
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
            role=UserRole(user.role).value,
        )
        new_refresh = create_refresh_token(
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    # ── Forgot / Reset / Change Password ──────────────────────────────────────

    async def forgot_password(self, email: str) -> "PasswordChangeResponse":
        from app.schemas.auth import PasswordChangeResponse
        from app.services.password_service import PasswordService
        from app.services.email_service import send_reset_link

        # Busca sem revelar se o usuário existe (segurança anti-enumeração)
        result = await self._user_repo.get_by_email_global(email)

        if result:
            svc = PasswordService(self._session)
            token = await svc.criar_token_reset(result.id)
            await self._session.commit()
            await send_reset_link(result.email, result.full_name, token)

        return PasswordChangeResponse(
            message="Se este e-mail estiver cadastrado, você receberá um link em instantes."
        )

    async def reset_password(self, token: str, new_password: str) -> "PasswordChangeResponse":
        from app.schemas.auth import PasswordChangeResponse
        from app.services.password_service import PasswordService

        svc = PasswordService(self._session)
        token_record = await svc.validar_token_reset(token)

        if token_record is None:
            raise AuthenticationException("Token inválido ou expirado")

        user = await self._user_repo.get_by_id(token_record.user_id)
        if user is None or not user.active:
            raise AuthenticationException("Usuário não encontrado ou inativo")

        user.hashed_password = hash_password(new_password)
        user.precisa_trocar_senha = False
        await self._user_repo.save(user)
        await svc.consumir_token(token_record)
        await self._session.commit()

        return PasswordChangeResponse(message="Senha redefinida com sucesso.")

    async def change_password(self, current_user, current_password: str, new_password: str) -> "PasswordChangeResponse":
        from app.schemas.auth import PasswordChangeResponse

        if not verify_password(current_password, current_user.hashed_password):
            raise AuthenticationException("Senha atual incorreta")

        current_user.hashed_password = hash_password(new_password)
        current_user.precisa_trocar_senha = False
        await self._user_repo.save(current_user)
        await self._session.commit()

        return PasswordChangeResponse(message="Senha alterada com sucesso.")
