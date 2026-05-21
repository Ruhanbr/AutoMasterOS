"""
Testes de integração — AuthService.

Cobre:
  - Registro de usuário (admin e técnico)
  - Login com credenciais válidas e inválidas
  - Atualização de last_login_at
  - Renovação de token via refresh
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationException, BusinessRuleException, ResourceNotFoundException
from app.core.security import create_refresh_token, hash_password, verify_password
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.auth import LoginRequest, UserCreate
from app.services.auth_service import AuthService

pytestmark = pytest.mark.integration


# ─── Registro ─────────────────────────────────────────────────────────────────

class TestRegistration:
    async def test_cria_usuario_admin(self, db_session: AsyncSession, tenant: Tenant):
        svc = AuthService(db_session)
        user = await svc.register(
            UserCreate(
                email="admin@oficina.com",
                password="senhaforte123",
                full_name="Gerente da Oficina",
                role=UserRole.ADMIN,
                tenant_id=tenant.id,
            )
        )

        assert user.id is not None
        assert user.email == "admin@oficina.com"
        assert user.role == UserRole.ADMIN
        assert user.tenant_id == tenant.id
        assert user.active is True
        # Senha deve estar hasheada — nunca em texto claro
        assert user.hashed_password != "senhaforte123"
        assert verify_password("senhaforte123", user.hashed_password)

    async def test_cria_usuario_tecnico(self, db_session: AsyncSession, tenant: Tenant):
        svc = AuthService(db_session)
        user = await svc.register(
            UserCreate(
                email="tecnico@oficina.com",
                password="senhaforte123",
                full_name="Carlos Mecânico",
                role=UserRole.TECNICO,
                tenant_id=tenant.id,
            )
        )
        assert user.role == UserRole.TECNICO

    async def test_rejeita_email_duplicado_no_mesmo_tenant(
        self, db_session: AsyncSession, tenant: Tenant
    ):
        svc = AuthService(db_session)
        data = UserCreate(
            email="duplicado@oficina.com",
            password="senhaforte123",
            full_name="Primeiro",
            tenant_id=tenant.id,
        )
        await svc.register(data)

        with pytest.raises(BusinessRuleException, match="já cadastrado"):
            await svc.register(
                UserCreate(
                    email="duplicado@oficina.com",
                    password="outrasenha123",
                    full_name="Segundo",
                    tenant_id=tenant.id,
                )
            )

    async def test_rejeita_tenant_inexistente(self, db_session: AsyncSession):
        svc = AuthService(db_session)
        with pytest.raises(ResourceNotFoundException):
            await svc.register(
                UserCreate(
                    email="ninguem@oficina.com",
                    password="senhaforte123",
                    full_name="Fantasma",
                    tenant_id=uuid.uuid4(),  # não existe
                )
            )


# ─── Login ────────────────────────────────────────────────────────────────────

class TestLogin:
    async def _criar_usuario(
        self, db_session: AsyncSession, tenant: Tenant, email: str = "user@teste.com"
    ) -> User:
        svc = AuthService(db_session)
        return await svc.register(
            UserCreate(
                email=email,
                password="senha123456",
                full_name="Usuário Teste",
                tenant_id=tenant.id,
            )
        )

    async def test_login_valido_retorna_tokens(
        self, db_session: AsyncSession, tenant: Tenant
    ):
        await self._criar_usuario(db_session, tenant)

        svc = AuthService(db_session)
        response = await svc.login(
            LoginRequest(email="user@teste.com", password="senha123456", tenant_id=tenant.id)
        )

        assert response.access_token
        assert response.refresh_token
        assert response.token_type == "bearer"
        assert response.expires_in > 0

    async def test_login_atualiza_last_login_at(
        self, db_session: AsyncSession, tenant: Tenant
    ):
        user = await self._criar_usuario(db_session, tenant)
        assert user.last_login_at is None

        svc = AuthService(db_session)
        await svc.login(
            LoginRequest(email="user@teste.com", password="senha123456", tenant_id=tenant.id)
        )

        await db_session.refresh(user)
        assert user.last_login_at is not None

    async def test_login_falha_senha_errada(
        self, db_session: AsyncSession, tenant: Tenant
    ):
        await self._criar_usuario(db_session, tenant)

        svc = AuthService(db_session)
        with pytest.raises(AuthenticationException):
            await svc.login(
                LoginRequest(
                    email="user@teste.com",
                    password="senhaerrada",
                    tenant_id=tenant.id,
                )
            )

    async def test_login_falha_email_inexistente(
        self, db_session: AsyncSession, tenant: Tenant
    ):
        svc = AuthService(db_session)
        with pytest.raises(AuthenticationException):
            await svc.login(
                LoginRequest(
                    email="naoexiste@teste.com",
                    password="qualquer123",
                    tenant_id=tenant.id,
                )
            )

    async def test_login_falha_usuario_inativo(
        self, db_session: AsyncSession, tenant: Tenant
    ):
        user = await self._criar_usuario(db_session, tenant)
        user.active = False
        db_session.add(user)
        await db_session.flush()

        svc = AuthService(db_session)
        with pytest.raises(AuthenticationException):
            await svc.login(
                LoginRequest(
                    email="user@teste.com",
                    password="senha123456",
                    tenant_id=tenant.id,
                )
            )


# ─── Refresh ──────────────────────────────────────────────────────────────────

class TestRefresh:
    async def test_refresh_retorna_novo_access_token(
        self, db_session: AsyncSession, tenant: Tenant
    ):
        svc = AuthService(db_session)
        user = await svc.register(
            UserCreate(
                email="refresh@teste.com",
                password="senha123456",
                full_name="Refresh User",
                tenant_id=tenant.id,
            )
        )
        token_resp = await svc.login(
            LoginRequest(
                email="refresh@teste.com", password="senha123456", tenant_id=tenant.id
            )
        )

        new_resp = await svc.refresh(token_resp.refresh_token)
        assert new_resp.access_token
        assert new_resp.refresh_token
        # Novo access token é diferente (timestamp na expiração muda)
        # (pode ser igual se emitido no mesmo segundo — verificamos apenas que existe)
        assert new_resp.token_type == "bearer"

    async def test_refresh_rejeita_token_invalido(self, db_session: AsyncSession):
        svc = AuthService(db_session)
        with pytest.raises(AuthenticationException):
            await svc.refresh("token.totalmente.invalido")

    async def test_refresh_rejeita_access_token_como_refresh(
        self, db_session: AsyncSession, tenant: Tenant
    ):
        svc = AuthService(db_session)
        user = await svc.register(
            UserCreate(
                email="wrongtype@teste.com",
                password="senha123456",
                full_name="Wrong Type",
                tenant_id=tenant.id,
            )
        )
        # Usa access token onde deveria ser refresh
        from app.core.security import create_access_token
        access = create_access_token(str(user.id), str(user.tenant_id), UserRole(user.role).value)

        with pytest.raises(AuthenticationException, match="refresh"):
            await svc.refresh(access)
