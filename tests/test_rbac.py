"""
test_rbac.py — testes de isolamento multi-tenant e controle de acesso por papel.

Cobre os 6 gaps identificados na auditoria:
  1. TECNICO não pode criar usuários (POST /users → 403)
  2. TECNICO vê apenas suas próprias OS na listagem
  3. TECNICO não consegue buscar OS de outro técnico (→ 404)
  4. ADMIN vê todas as OS do tenant
  5. Desativar técnico com OS aberta → 422
  6. Criar OS como TECNICO auto-preenche technician_user_id
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client, DocumentType
from app.models.service_order import ServiceOrder, ServiceOrderStatus
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from tests.conftest import auth_headers


# ── Helpers de factory ────────────────────────────────────────────────────────

async def _make_tenant(session: AsyncSession) -> Tenant:
    """Cria tenant com documento único para evitar colisões entre testes."""
    uid = uuid.uuid4().hex[:8]
    t = Tenant(
        id=uuid.uuid4(),
        name=f"Oficina RBAC {uid}",
        document=f"{uid[:8]}000190"[:14].ljust(14, "0"),
        email=f"rbac_{uid}@test.com",
        razao_social=f"OFICINA RBAC {uid} LTDA",
        crt="1",
        active=True,
    )
    session.add(t)
    await session.flush()
    return t


async def _make_user(
    session: AsyncSession,
    tenant: Tenant,
    role: UserRole,
    email: str | None = None,
) -> User:
    from app.core.security import hash_password

    u = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=email or f"{role.value.lower()}_{uuid.uuid4().hex[:6]}@rbac.test",
        hashed_password=hash_password("Senha@123"),
        full_name=f"Usuário {role.value}",
        role=role,
        active=True,
    )
    session.add(u)
    await session.flush()
    return u


async def _make_os(
    session: AsyncSession,
    tenant: Tenant,
    client: Client,
    number: int,
    technician_user_id: uuid.UUID | None = None,
    status: ServiceOrderStatus = ServiceOrderStatus.ABERTA,
) -> ServiceOrder:
    so = ServiceOrder(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        client_id=client.id,
        number=number,
        status=status,
        description="OS de teste RBAC",
        opened_at=datetime.now(timezone.utc),
        total_services=Decimal("0.00"),
        total_parts=Decimal("0.00"),
        total_discount=Decimal("0.00"),
        total_amount=Decimal("0.00"),
        technician_user_id=technician_user_id,
    )
    session.add(so)
    await session.flush()
    return so


async def _make_client(session: AsyncSession, tenant: Tenant) -> Client:
    # CPF aleatório de 11 dígitos numéricos
    doc = str(uuid.uuid4().int)[:11].ljust(11, "0")
    c = Client(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name=f"Cliente RBAC {uuid.uuid4().hex[:4]}",
        document=doc,
        document_type=DocumentType.CPF,
        active=True,
    )
    session.add(c)
    await session.flush()
    return c


# ── 1. TECNICO não pode criar usuários ───────────────────────────────────────

@pytest.mark.asyncio
async def test_tecnico_nao_pode_criar_usuario(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """TECNICO tentando POST /users deve receber 403."""
    t = await _make_tenant(db_session)
    tecnico = await _make_user(db_session, t, UserRole.TECNICO)

    response = await http_client.post(
        "/api/v1/users",
        json={
            "full_name": "Novo Técnico",
            "email": f"novo_{uuid.uuid4().hex[:6]}@test.com",
            "password": "Senha@123",
            "role": "TECNICO",
        },
        headers={**auth_headers(tecnico), "X-Tenant-ID": str(t.id)},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_admin_pode_criar_usuario(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """ADMIN pode criar usuários normalmente."""
    t = await _make_tenant(db_session)
    admin = await _make_user(db_session, t, UserRole.ADMIN)

    response = await http_client.post(
        "/api/v1/users",
        json={
            "full_name": "Técnico Novo",
            "email": f"tec_{uuid.uuid4().hex[:6]}@test.com",
            "password": "Senha@123",
            "role": "TECNICO",
        },
        headers={**auth_headers(admin), "X-Tenant-ID": str(t.id)},
    )
    assert response.status_code == 201, response.text


# ── 2. TECNICO vê apenas suas próprias OS ────────────────────────────────────

@pytest.mark.asyncio
async def test_tecnico_ve_apenas_proprias_os(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """TECNICO lista OS → retorna apenas as vinculadas a ele."""
    t = await _make_tenant(db_session)
    tec_a = await _make_user(db_session, t, UserRole.TECNICO)
    tec_b = await _make_user(db_session, t, UserRole.TECNICO)
    cli = await _make_client(db_session, t)

    os_a = await _make_os(db_session, t, cli, number=101, technician_user_id=tec_a.id)
    os_b = await _make_os(db_session, t, cli, number=102, technician_user_id=tec_b.id)

    response = await http_client.get(
        "/api/v1/service-orders",
        headers={**auth_headers(tec_a), "X-Tenant-ID": str(t.id)},
    )
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert str(os_a.id) in ids, "OS do próprio técnico deve aparecer"
    assert str(os_b.id) not in ids, "OS de outro técnico NÃO deve aparecer"


# ── 3. TECNICO não busca OS de outro técnico ─────────────────────────────────

@pytest.mark.asyncio
async def test_tecnico_nao_ve_os_de_outro_tecnico(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """GET /service-orders/{id} por TECNICO → 404 se não for a OS dele."""
    t = await _make_tenant(db_session)
    tec_a = await _make_user(db_session, t, UserRole.TECNICO)
    tec_b = await _make_user(db_session, t, UserRole.TECNICO)
    cli = await _make_client(db_session, t)

    os_b = await _make_os(db_session, t, cli, number=201, technician_user_id=tec_b.id)

    response = await http_client.get(
        f"/api/v1/service-orders/{os_b.id}",
        headers={**auth_headers(tec_a), "X-Tenant-ID": str(t.id)},
    )
    # 404 — evita information disclosure
    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_tecnico_ve_propria_os_por_id(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """GET /service-orders/{id} pelo próprio técnico → 200."""
    t = await _make_tenant(db_session)
    tec = await _make_user(db_session, t, UserRole.TECNICO)
    cli = await _make_client(db_session, t)
    os_ = await _make_os(db_session, t, cli, number=202, technician_user_id=tec.id)

    response = await http_client.get(
        f"/api/v1/service-orders/{os_.id}",
        headers={**auth_headers(tec), "X-Tenant-ID": str(t.id)},
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(os_.id)


# ── 4. ADMIN vê todas as OS do tenant ────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_ve_todas_os_do_tenant(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """ADMIN lista OS → vê as de todos os técnicos do tenant."""
    t = await _make_tenant(db_session)
    admin = await _make_user(db_session, t, UserRole.ADMIN)
    tec_a = await _make_user(db_session, t, UserRole.TECNICO)
    tec_b = await _make_user(db_session, t, UserRole.TECNICO)
    cli = await _make_client(db_session, t)

    os_a = await _make_os(db_session, t, cli, number=301, technician_user_id=tec_a.id)
    os_b = await _make_os(db_session, t, cli, number=302, technician_user_id=tec_b.id)

    response = await http_client.get(
        "/api/v1/service-orders",
        headers={**auth_headers(admin), "X-Tenant-ID": str(t.id)},
    )
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert str(os_a.id) in ids
    assert str(os_b.id) in ids


# ── 5. Desativar técnico com OS aberta → 422 ─────────────────────────────────

@pytest.mark.asyncio
async def test_delete_tecnico_com_os_aberta_bloqueado(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """DELETE /users/{id} com OS aberta → 422 com mensagem explicativa."""
    t = await _make_tenant(db_session)
    admin = await _make_user(db_session, t, UserRole.ADMIN)
    tec = await _make_user(db_session, t, UserRole.TECNICO)
    cli = await _make_client(db_session, t)

    await _make_os(db_session, t, cli, number=401, technician_user_id=tec.id)

    response = await http_client.delete(
        f"/api/v1/users/{tec.id}",
        headers={**auth_headers(admin), "X-Tenant-ID": str(t.id)},
    )
    assert response.status_code == 422
    detail = response.json()["detail"].lower()
    assert "os" in detail or "ordens" in detail


@pytest.mark.asyncio
async def test_delete_tecnico_sem_os_permitido(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """DELETE /users/{id} sem OS abertas → 204."""
    t = await _make_tenant(db_session)
    admin = await _make_user(db_session, t, UserRole.ADMIN)
    tec = await _make_user(db_session, t, UserRole.TECNICO)

    response = await http_client.delete(
        f"/api/v1/users/{tec.id}",
        headers={**auth_headers(admin), "X-Tenant-ID": str(t.id)},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_tecnico_nao_pode_desativar_usuario(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """TECNICO tentando DELETE /users/{id} → 403."""
    t = await _make_tenant(db_session)
    tec_a = await _make_user(db_session, t, UserRole.TECNICO)
    tec_b = await _make_user(db_session, t, UserRole.TECNICO)

    response = await http_client.delete(
        f"/api/v1/users/{tec_b.id}",
        headers={**auth_headers(tec_a), "X-Tenant-ID": str(t.id)},
    )
    assert response.status_code == 403


# ── 6. Criar OS como TECNICO auto-preenche technician_user_id ────────────────

@pytest.mark.asyncio
async def test_criar_os_como_tecnico_auto_assina(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """Quando TECNICO cria OS, technician_user_id é preenchido com seu próprio ID."""
    t = await _make_tenant(db_session)
    tec = await _make_user(db_session, t, UserRole.TECNICO)
    cli = await _make_client(db_session, t)
    cli.active = True
    await db_session.flush()

    response = await http_client.post(
        "/api/v1/service-orders",
        json={
            "client_id": str(cli.id),
            "description": "Manutenção preventiva auto-assinada",
        },
        headers={**auth_headers(tec), "X-Tenant-ID": str(t.id)},
    )
    assert response.status_code == 201, response.text
    data = response.json()

    from sqlalchemy import select
    result = await db_session.execute(
        select(ServiceOrder).where(ServiceOrder.id == uuid.UUID(data["id"]))
    )
    os_ = result.scalar_one()
    assert os_.technician_user_id == tec.id, (
        f"OS criada por TECNICO deve ter technician_user_id={tec.id}, "
        f"encontrou {os_.technician_user_id}"
    )


# ── Bonus: isolamento entre tenants ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_nao_ve_os_de_outro_tenant(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """ADMIN de um tenant não enxerga OS de outro tenant."""
    t_a = await _make_tenant(db_session)
    t_b = await _make_tenant(db_session)

    admin_a = await _make_user(db_session, t_a, UserRole.ADMIN)
    cli_b = await _make_client(db_session, t_b)
    os_b = await _make_os(db_session, t_b, cli_b, number=501)

    response = await http_client.get(
        "/api/v1/service-orders",
        headers={**auth_headers(admin_a), "X-Tenant-ID": str(t_a.id)},
    )
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert str(os_b.id) not in ids, "OS de outro tenant NÃO deve aparecer"
