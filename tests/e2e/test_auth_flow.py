"""
Testes E2E — Fluxo de autenticação via API REST.

Cobre:
  - Registro + login + uso de token em rota protegida
  - GET /auth/me com token válido
  - POST /auth/refresh
  - Rotas protegidas sem token → 401
  - Token inválido → 401
  - Credenciais erradas no login → 401
"""

import uuid

import pytest

from app.models.tenant import Tenant

pytestmark = pytest.mark.e2e


class TestAuthEndpoints:
    async def test_registro_e_login_completo(self, http_client, tenant: Tenant):
        """Registra usuário e faz login — verifica tokens retornados."""
        # Registro
        resp = await http_client.post(
            "/api/v1/auth/register",
            json={
                "email": "novo@oficina.com",
                "password": "senhaforte123",
                "full_name": "Novo Usuário",
                "role": "TECNICO",
                "tenant_id": str(tenant.id),
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["email"] == "novo@oficina.com"
        assert data["role"] == "TECNICO"
        assert "hashed_password" not in data

        # Login
        resp = await http_client.post(
            "/api/v1/auth/login",
            json={
                "email": "novo@oficina.com",
                "password": "senhaforte123",
                "tenant_id": str(tenant.id),
            },
        )
        assert resp.status_code == 200, resp.text
        tokens = resp.json()
        assert tokens["access_token"]
        assert tokens["refresh_token"]
        assert tokens["token_type"] == "bearer"
        assert tokens["expires_in"] > 0

    async def test_me_retorna_dados_do_usuario(self, http_client, user_admin):
        """GET /auth/me retorna os dados do usuário autenticado."""
        from tests.conftest import auth_headers

        resp = await http_client.get("/api/v1/auth/me", headers=auth_headers(user_admin))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["email"] == user_admin.email
        assert data["role"] == user_admin.role.value
        assert data["tenant_id"] == str(user_admin.tenant_id)

    async def test_refresh_token_emite_novo_access_token(self, http_client, user_admin):
        """POST /auth/refresh com refresh token válido retorna novo par de tokens."""
        from app.core.security import create_refresh_token

        refresh = create_refresh_token(str(user_admin.id), str(user_admin.tenant_id))
        resp = await http_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["access_token"]
        assert data["refresh_token"]

    async def test_rota_protegida_sem_token_retorna_401(self, http_client):
        """Requisição sem Authorization header → 401.
        HTTPException do FastAPI retorna {"detail": {...}}."""
        resp = await http_client.get("/api/v1/clients")
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "UNAUTHORIZED"

    async def test_rota_protegida_token_invalido_retorna_401(self, http_client):
        """Bearer token com assinatura errada → 401."""
        resp = await http_client.get(
            "/api/v1/clients",
            headers={"Authorization": "Bearer token.invalido.aqui"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "UNAUTHORIZED"

    async def test_login_credenciais_erradas_retorna_401(self, http_client, tenant: Tenant):
        """Login com senha errada → 401.
        AuthenticationException usa handler customizado → {"code": ...} (sem wrapper "detail")."""
        resp = await http_client.post(
            "/api/v1/auth/login",
            json={
                "email": "naoexiste@oficina.com",
                "password": "senhaerrada123",
                "tenant_id": str(tenant.id),
            },
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == "AUTHENTICATION_ERROR"
