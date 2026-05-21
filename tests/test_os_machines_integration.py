"""
Testes de integração: Máquinas na OS + Clientes avançado.

Cenários cobertos:
1. test_os_com_maquina_end2end          — OS criada com máquina; machine embutida na resposta
2. test_maquina_diferente_cliente_falha — máquina pertence a outro cliente → 422
3. test_cliente_desativado_bloqueia_os  — cliente inativo → 422
4. test_machines_por_cliente_endpoint   — GET /machines/client/{id} retorna só máquinas do cliente
5. test_post_deactivate_cliente_204     — POST /clients/{id}/deactivate → 204
6. test_reativar_cliente_via_patch      — PATCH /clients/{id} com active=true reativa cliente
"""

import uuid

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.client import Client, DocumentType
from app.models.machine import Machine, MachineType
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.client_service import ClientService

pytestmark = pytest.mark.asyncio


# ── helpers ───────────────────────────────────────────────────────────────────

def _auth_headers(user: User) -> dict:
    token = create_access_token(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        role=UserRole(user.role).value,
    )
    return {"Authorization": f"Bearer {token}"}


async def _make_client(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    suffix: str = "",
    active: bool = True,
) -> Client:
    c = Client(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=f"Cliente {suffix}",
        document=f"0000000000{suffix[-1] if suffix else '9'}",
        document_type=DocumentType.CPF,
        phone="11999990000",
        municipio="Goiânia",
        uf="GO",
        cep="74000000",
        codigo_municipio="5208707",
        logradouro="Av. Goiás",
        numero="1",
        bairro="Centro",
        active=active,
    )
    session.add(c)
    await session.flush()
    return c


async def _make_machine(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    client_id: uuid.UUID,
    serial: str | None = None,
) -> Machine:
    m = Machine(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        client_id=client_id,
        machine_type=MachineType.TRATORES.value,
        brand="John Deere",
        model="7200",
        serial_number=serial or f"SN-{uuid.uuid4().hex[:8].upper()}",
        year=2022,
        active=True,
    )
    session.add(m)
    await session.flush()
    return m


# ── 1. OS com máquina — end-to-end ───────────────────────────────────────────

async def test_os_com_maquina_end2end(
    db_session: AsyncSession,
    tenant: Tenant,
    client_entity: Client,
    user_admin: User,
):
    """Criar OS com machine_id válido → resposta inclui 'machine' embutido."""
    machine = await _make_machine(db_session, tenant.id, client_entity.id)

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    headers = _auth_headers(user_admin)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test/api/v1",
            follow_redirects=True,
        ) as client:
            resp = await client.post(
                "/service-orders/",
                json={
                    "client_id": str(client_entity.id),
                    "machine_id": str(machine.id),
                    "description": "Troca de óleo e filtros",
                },
                headers=headers,
            )

        assert resp.status_code == 201, resp.text
        data = resp.json()

        # machine embutido na resposta
        assert data["machine_id"] == str(machine.id)
        assert data["machine"] is not None
        assert data["machine"]["id"] == str(machine.id)
        assert data["machine"]["brand"] == "John Deere"
        assert data["machine"]["model"] == "7200"
        assert data["machine"]["serial_number"] == machine.serial_number

        # cliente embutido também
        assert data["client"]["id"] == str(client_entity.id)
    finally:
        app.dependency_overrides.clear()


# ── 2. Máquina de outro cliente → 422 ────────────────────────────────────────

async def test_maquina_diferente_cliente_falha(
    db_session: AsyncSession,
    tenant: Tenant,
    client_entity: Client,
    user_admin: User,
):
    """Máquina pertence ao cliente B; OS é aberta para o cliente A → 422."""
    # cliente B tem sua própria máquina
    client_b = await _make_client(db_session, tenant.id, suffix="B")
    machine_b = await _make_machine(db_session, tenant.id, client_b.id)

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    headers = _auth_headers(user_admin)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test/api/v1",
            follow_redirects=True,
        ) as client:
            resp = await client.post(
                "/service-orders/",
                json={
                    "client_id": str(client_entity.id),   # cliente A
                    "machine_id": str(machine_b.id),       # máquina do cliente B
                    "description": "Revisão cruzada",
                },
                headers=headers,
            )

        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert "não pertence ao cliente" in detail["message"]
    finally:
        app.dependency_overrides.clear()


# ── 3. Cliente inativo bloqueia criação de OS ─────────────────────────────────

async def test_cliente_desativado_bloqueia_os(
    db_session: AsyncSession,
    tenant: Tenant,
    user_admin: User,
):
    """Cliente inativo não pode abrir OS → 422."""
    # criar cliente já inativo
    inactive_client = await _make_client(db_session, tenant.id, suffix="I", active=False)

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    headers = _auth_headers(user_admin)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test/api/v1",
            follow_redirects=True,
        ) as client:
            resp = await client.post(
                "/service-orders/",
                json={
                    "client_id": str(inactive_client.id),
                    "description": "Serviço bloqueado",
                },
                headers=headers,
            )

        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert "inativo" in detail["message"].lower()
    finally:
        app.dependency_overrides.clear()


# ── 4. GET /machines/client/{id} — isolamento por cliente ────────────────────

async def test_machines_por_cliente_endpoint(
    db_session: AsyncSession,
    tenant: Tenant,
    client_entity: Client,
    user_admin: User,
):
    """Endpoint retorna apenas máquinas do cliente especificado."""
    client_b = await _make_client(db_session, tenant.id, suffix="Z")

    # 2 máquinas do cliente A, 1 do cliente B
    m1 = await _make_machine(db_session, tenant.id, client_entity.id)
    m2 = await _make_machine(db_session, tenant.id, client_entity.id)
    m_b = await _make_machine(db_session, tenant.id, client_b.id)

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    headers = _auth_headers(user_admin)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test/api/v1",
            follow_redirects=True,
        ) as client:
            resp = await client.get(
                f"/machines/client/{client_entity.id}",
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        ids = {item["id"] for item in data["items"]}
        assert str(m1.id) in ids
        assert str(m2.id) in ids
        assert str(m_b.id) not in ids  # isolamento
    finally:
        app.dependency_overrides.clear()


# ── 5. POST /clients/{id}/deactivate → 204 ───────────────────────────────────

async def test_post_deactivate_cliente_204(
    db_session: AsyncSession,
    tenant: Tenant,
    client_entity: Client,
    user_admin: User,
):
    """POST /clients/{id}/deactivate retorna 204 e cliente fica inativo."""
    async def override_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    headers = _auth_headers(user_admin)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test/api/v1",
            follow_redirects=True,
        ) as client:
            resp = await client.post(
                f"/clients/{client_entity.id}/deactivate",
                headers=headers,
            )
            assert resp.status_code == 204, resp.text
            assert resp.content == b""  # sem body

            # verificar estado no DB via GET
            resp_get = await client.get(
                f"/clients/{client_entity.id}",
                headers=headers,
            )

        assert resp_get.status_code == 200
        assert resp_get.json()["active"] is False
    finally:
        app.dependency_overrides.clear()


# ── 6. PATCH /clients/{id} reativa cliente ────────────────────────────────────

async def test_reativar_cliente_via_patch(
    db_session: AsyncSession,
    tenant: Tenant,
    user_admin: User,
):
    """PATCH /clients/{id} com active=true reativa um cliente inativo."""
    inactive = await _make_client(db_session, tenant.id, suffix="R", active=False)

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    headers = _auth_headers(user_admin)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test/api/v1",
            follow_redirects=True,
        ) as client:
            resp = await client.patch(
                f"/clients/{inactive.id}",
                json={"active": True, "name": "Cliente Reativado"},
                headers=headers,
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["active"] is True
        assert data["name"] == "Cliente Reativado"
    finally:
        app.dependency_overrides.clear()
