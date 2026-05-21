"""
Testes para reset de senha por email (forgot-password / reset-password).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.password_reset_token import PasswordResetToken
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.password_service import PasswordService


class TestPasswordReset:

    @pytest.mark.asyncio
    async def test_forgot_password_sempre_retorna_200(
        self,
        http_client: AsyncClient,
        tenant: Tenant,
    ) -> None:
        """Mesmo com email inexistente, retorna 200 (anti-enumeração)."""
        r = await http_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "naoexiste@nowhere.com"},
        )
        assert r.status_code == 200, r.text
        assert "receberá" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_criar_e_validar_token_reset(
        self,
        db_session: AsyncSession,
        tenant: Tenant,
    ) -> None:
        """Token criado deve ser válido imediatamente."""
        u = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="reset_tok@teste.com",
            hashed_password=hash_password("Senha123!"),
            full_name="Reset Token User",
            role=UserRole.ADMIN,
            active=True,
            precisa_trocar_senha=False,
        )
        db_session.add(u)
        await db_session.flush()

        svc = PasswordService(db_session)
        token = await svc.criar_token_reset(u.id)
        assert token

        record = await svc.validar_token_reset(token)
        assert record is not None
        assert record.user_id == u.id
        assert not record.used

    @pytest.mark.asyncio
    async def test_token_usado_invalido(
        self,
        db_session: AsyncSession,
        tenant: Tenant,
    ) -> None:
        """Token marcado como usado não pode ser reutilizado."""
        u = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="used_tok@teste.com",
            hashed_password=hash_password("Senha123!"),
            full_name="Used Token User",
            role=UserRole.ADMIN,
            active=True,
            precisa_trocar_senha=False,
        )
        db_session.add(u)
        await db_session.flush()

        svc = PasswordService(db_session)
        token = await svc.criar_token_reset(u.id)
        record = await svc.validar_token_reset(token)
        await svc.consumir_token(record)

        record2 = await svc.validar_token_reset(token)
        assert record2 is None

    @pytest.mark.asyncio
    async def test_token_expirado_invalido(
        self,
        db_session: AsyncSession,
        tenant: Tenant,
    ) -> None:
        """Token com expires_at no passado não é válido."""
        u = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="exp_tok@teste.com",
            hashed_password=hash_password("Senha123!"),
            full_name="Expired Token User",
            role=UserRole.ADMIN,
            active=True,
            precisa_trocar_senha=False,
        )
        db_session.add(u)
        await db_session.flush()

        expired = PasswordResetToken(
            id=uuid.uuid4(),
            user_id=u.id,
            token="token-expirado-abc123",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=2),
            used=False,
        )
        db_session.add(expired)
        await db_session.flush()

        svc = PasswordService(db_session)
        result = await svc.validar_token_reset("token-expirado-abc123")
        assert result is None

    @pytest.mark.asyncio
    async def test_reset_password_via_endpoint(
        self,
        http_client: AsyncClient,
        db_session: AsyncSession,
        tenant: Tenant,
    ) -> None:
        """POST /auth/reset-password deve trocar senha com token válido."""
        senha_original = "SenhaOriginal123!"
        u = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="reset_end@teste.com",
            hashed_password=hash_password(senha_original),
            full_name="Reset Endpoint User",
            role=UserRole.ADMIN,
            active=True,
            precisa_trocar_senha=False,
        )
        db_session.add(u)
        await db_session.flush()

        svc = PasswordService(db_session)
        token = await svc.criar_token_reset(u.id)
        await db_session.flush()

        r = await http_client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "NovaSenhaForte456!"},
        )
        assert r.status_code == 200, r.text
        assert "sucesso" in r.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_reset_password_token_invalido_retorna_401(
        self,
        http_client: AsyncClient,
    ) -> None:
        """Token inválido deve retornar 401."""
        r = await http_client.post(
            "/api/v1/auth/reset-password",
            json={"token": "token-inexistente-xyz", "new_password": "NovaSenha456!"},
        )
        assert r.status_code == 401, r.text

    @pytest.mark.asyncio
    async def test_gerar_senha_temporaria_formato(self) -> None:
        """Senha gerada deve ter tamanho e complexidade corretos."""
        for _ in range(10):
            senha = PasswordService.gerar_senha_temporaria()
            assert len(senha) == 12
            assert any(c.isupper() for c in senha)
            assert any(c.islower() for c in senha)
            assert any(c.isdigit() for c in senha)
            assert any(c in "!@#$%" for c in senha)

    @pytest.mark.asyncio
    async def test_novo_token_invalida_token_anterior(
        self,
        db_session: AsyncSession,
        tenant: Tenant,
    ) -> None:
        """Criar segundo token deve invalidar o primeiro."""
        u = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email="two_tok@teste.com",
            hashed_password=hash_password("Senha123!"),
            full_name="Two Token User",
            role=UserRole.ADMIN,
            active=True,
            precisa_trocar_senha=False,
        )
        db_session.add(u)
        await db_session.flush()

        svc = PasswordService(db_session)
        token1 = await svc.criar_token_reset(u.id)
        await db_session.flush()
        token2 = await svc.criar_token_reset(u.id)
        await db_session.flush()

        assert await svc.validar_token_reset(token1) is None  # invalidado
        assert await svc.validar_token_reset(token2) is not None  # válido
