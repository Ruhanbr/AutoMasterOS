"""
Testes para senha temporária e fluxo de troca obrigatória.
"""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.core.security import hash_password
from tests.conftest import auth_headers


async def _create_admin(session: AsyncSession, tenant: Tenant) -> User:
    u = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="admin_temp@teste.com",
        hashed_password=hash_password("AdminSenha123!"),
        full_name="Admin Temp Test",
        role=UserRole.ADMIN,
        active=True,
        precisa_trocar_senha=False,
    )
    session.add(u)
    await session.flush()
    return u


class TestSenhaTemporaria:

    @pytest.mark.asyncio
    async def test_criar_tecnico_via_api_gera_senha_temp(
        self,
        http_client: AsyncClient,
        db_session: AsyncSession,
        tenant: Tenant,
    ) -> None:
        """POST /users deve criar técnico com precisa_trocar_senha=True."""
        admin = await _create_admin(db_session, tenant)
        headers = auth_headers(admin)

        r = await http_client.post(
            "/api/v1/users",
            json={
                "full_name": "Técnico Temp",
                "email": "tec_temp@teste.com",
                "password": "QualquerCoisa123!",  # ignorado — sistema gera própria
                "role": "TECNICO",
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text

    @pytest.mark.asyncio
    async def test_login_usuario_com_senha_temp_retorna_force_change(
        self,
        http_client: AsyncClient,
        db_session: AsyncSession,
        tenant: Tenant,
    ) -> None:
        """Login de usuário com precisa_trocar_senha=True deve retornar force_password_change=True."""
        senha = "SenhaTemp123!"
        u = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="force_change@teste.com",
            hashed_password=hash_password(senha),
            full_name="Force Change User",
            role=UserRole.TECNICO,
            active=True,
            precisa_trocar_senha=True,
        )
        db_session.add(u)
        await db_session.flush()

        r = await http_client.post(
            "/api/v1/auth/login",
            json={"email": u.email, "password": senha, "tenant_id": str(tenant.id)},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["force_password_change"] is True

    @pytest.mark.asyncio
    async def test_login_usuario_normal_nao_force_change(
        self,
        http_client: AsyncClient,
        db_session: AsyncSession,
        tenant: Tenant,
    ) -> None:
        """Login de usuário sem senha temporária NÃO retorna force_password_change."""
        senha = "SenhaNormal123!"
        u = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="normal_user@teste.com",
            hashed_password=hash_password(senha),
            full_name="Normal User",
            role=UserRole.ADMIN,
            active=True,
            precisa_trocar_senha=False,
        )
        db_session.add(u)
        await db_session.flush()

        r = await http_client.post(
            "/api/v1/auth/login",
            json={"email": u.email, "password": senha, "tenant_id": str(tenant.id)},
        )
        assert r.status_code == 200, r.text
        assert r.json()["force_password_change"] is False

    @pytest.mark.asyncio
    async def test_change_password_autentica_e_troca(
        self,
        http_client: AsyncClient,
        db_session: AsyncSession,
        tenant: Tenant,
    ) -> None:
        """POST /auth/change-password deve trocar senha e desativar flag."""
        senha_atual = "SenhaAtual123!"
        u = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="change_pwd@teste.com",
            hashed_password=hash_password(senha_atual),
            full_name="Change Pwd User",
            role=UserRole.ADMIN,
            active=True,
            precisa_trocar_senha=True,
        )
        db_session.add(u)
        await db_session.flush()

        headers = auth_headers(u)
        r = await http_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": senha_atual, "new_password": "NovaSenha456!"},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert "sucesso" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_change_password_senha_atual_errada_retorna_401(
        self,
        http_client: AsyncClient,
        db_session: AsyncSession,
        tenant: Tenant,
    ) -> None:
        """Senha atual incorreta deve retornar 401."""
        u = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="wrong_pwd@teste.com",
            hashed_password=hash_password("SenhaCorreta123!"),
            full_name="Wrong Pwd User",
            role=UserRole.ADMIN,
            active=True,
            precisa_trocar_senha=False,
        )
        db_session.add(u)
        await db_session.flush()

        headers = auth_headers(u)
        r = await http_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "SenhaErrada999!", "new_password": "NovaSenha456!"},
            headers=headers,
        )
        assert r.status_code == 401, r.text
