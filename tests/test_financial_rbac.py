"""
test_financial_rbac.py — testes de isolamento financeiro por papel.

Cobre:
  1. TECNICO vê apenas lançamentos financeiros vinculados às suas próprias OS
  2. TECNICO não vê lançamentos sem OS (despesas globais da oficina)
  3. TECNICO não vê lançamentos de OS de outro técnico
  4. ADMIN vê todos os lançamentos do tenant
  5. Resumo financeiro (summary) também é isolado por papel
  6. ADMIN de outro tenant não enxerga lançamentos financeiros alheios
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client, DocumentType
from app.models.service_order import ServiceOrder, ServiceOrderStatus
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.modules.financial.models import EntryType, FinancialEntry
from tests.conftest import auth_headers


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _make_tenant(session: AsyncSession) -> Tenant:
    uid = uuid.uuid4().hex[:8]
    t = Tenant(
        id=uuid.uuid4(),
        name=f"Oficina FIN {uid}",
        document=f"{uid[:8]}000190"[:14].ljust(14, "0"),
        email=f"fin_{uid}@test.com",
        razao_social=f"OFICINA FIN {uid} LTDA",
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
) -> User:
    from app.core.security import hash_password

    u = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=f"{role.value.lower()}_{uuid.uuid4().hex[:6]}@fin.test",
        hashed_password=hash_password("Senha@123"),
        full_name=f"Usuário {role.value}",
        role=role,
        active=True,
    )
    session.add(u)
    await session.flush()
    return u


async def _make_client(session: AsyncSession, tenant: Tenant) -> Client:
    doc = str(uuid.uuid4().int)[:11].ljust(11, "0")
    c = Client(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name=f"Cliente FIN {uuid.uuid4().hex[:4]}",
        document=doc,
        document_type=DocumentType.CPF,
        active=True,
    )
    session.add(c)
    await session.flush()
    return c


async def _make_os(
    session: AsyncSession,
    tenant: Tenant,
    client: Client,
    number: int,
    technician_user_id: uuid.UUID | None = None,
    status: ServiceOrderStatus = ServiceOrderStatus.FINALIZADA,
) -> ServiceOrder:
    so = ServiceOrder(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        client_id=client.id,
        number=number,
        status=status,
        description="OS financeiro RBAC",
        opened_at=datetime.now(timezone.utc),
        total_services=Decimal("100.00"),
        total_parts=Decimal("0.00"),
        total_discount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        technician_user_id=technician_user_id,
    )
    session.add(so)
    await session.flush()
    return so


async def _make_entry(
    session: AsyncSession,
    tenant: Tenant,
    amount: Decimal = Decimal("100.00"),
    entry_type: EntryType = EntryType.RECEITA,
    service_order_id: uuid.UUID | None = None,
    description: str = "Lançamento de teste",
) -> FinancialEntry:
    fe = FinancialEntry(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        entry_type=entry_type,
        amount=amount,
        description=description,
        reference_date=datetime.now(timezone.utc),
        service_order_id=service_order_id,
    )
    session.add(fe)
    await session.flush()
    return fe


# ── 1. TECNICO vê apenas lançamentos das suas OS ──────────────────────────────

@pytest.mark.asyncio
async def test_tecnico_ve_apenas_lancamentos_proprios(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """TECNICO lista /financial → retorna apenas entradas vinculadas às suas OS."""
    t = await _make_tenant(db_session)
    tec_a = await _make_user(db_session, t, UserRole.TECNICO)
    tec_b = await _make_user(db_session, t, UserRole.TECNICO)
    cli = await _make_client(db_session, t)

    os_a = await _make_os(db_session, t, cli, number=1001, technician_user_id=tec_a.id)
    os_b = await _make_os(db_session, t, cli, number=1002, technician_user_id=tec_b.id)

    entry_a = await _make_entry(db_session, t, service_order_id=os_a.id, description="Receita A")
    entry_b = await _make_entry(db_session, t, service_order_id=os_b.id, description="Receita B")

    response = await http_client.get(
        "/api/v1/financial",
        headers={**auth_headers(tec_a), "X-Tenant-ID": str(t.id)},
    )
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert str(entry_a.id) in ids, "Lançamento da própria OS deve aparecer"
    assert str(entry_b.id) not in ids, "Lançamento de OS de outro técnico NÃO deve aparecer"


# ── 2. TECNICO não vê despesas globais (sem service_order_id) ─────────────────

@pytest.mark.asyncio
async def test_tecnico_nao_ve_despesas_globais(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """Despesas sem OS vinculada são invisíveis para TECNICO."""
    t = await _make_tenant(db_session)
    tec = await _make_user(db_session, t, UserRole.TECNICO)

    # Despesa sem OS — lançamento global da oficina
    despesa_global = await _make_entry(
        db_session, t,
        entry_type=EntryType.DESPESA,
        service_order_id=None,
        description="Aluguel da oficina",
    )

    response = await http_client.get(
        "/api/v1/financial",
        headers={**auth_headers(tec), "X-Tenant-ID": str(t.id)},
    )
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert str(despesa_global.id) not in ids, "Despesas globais são invisíveis para TECNICO"


# ── 3. ADMIN vê tudo ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_ve_todos_lancamentos_do_tenant(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """ADMIN lista /financial → vê lançamentos de todos os técnicos + despesas globais."""
    t = await _make_tenant(db_session)
    admin = await _make_user(db_session, t, UserRole.ADMIN)
    tec_a = await _make_user(db_session, t, UserRole.TECNICO)
    tec_b = await _make_user(db_session, t, UserRole.TECNICO)
    cli = await _make_client(db_session, t)

    os_a = await _make_os(db_session, t, cli, number=2001, technician_user_id=tec_a.id)
    os_b = await _make_os(db_session, t, cli, number=2002, technician_user_id=tec_b.id)

    entry_a = await _make_entry(db_session, t, service_order_id=os_a.id, description="Receita tec_a")
    entry_b = await _make_entry(db_session, t, service_order_id=os_b.id, description="Receita tec_b")
    despesa = await _make_entry(
        db_session, t,
        entry_type=EntryType.DESPESA,
        service_order_id=None,
        description="Despesa global",
    )

    response = await http_client.get(
        "/api/v1/financial",
        headers={**auth_headers(admin), "X-Tenant-ID": str(t.id)},
    )
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert str(entry_a.id) in ids
    assert str(entry_b.id) in ids
    assert str(despesa.id) in ids


# ── 4. Summary financeiro isolado para TECNICO ────────────────────────────────

@pytest.mark.asyncio
async def test_tecnico_summary_inclui_apenas_proprias_os(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """GET /financial/summary para TECNICO deve somar apenas suas OS."""
    t = await _make_tenant(db_session)
    tec_a = await _make_user(db_session, t, UserRole.TECNICO)
    tec_b = await _make_user(db_session, t, UserRole.TECNICO)
    cli = await _make_client(db_session, t)

    os_a = await _make_os(db_session, t, cli, number=3001, technician_user_id=tec_a.id)
    os_b = await _make_os(db_session, t, cli, number=3002, technician_user_id=tec_b.id)

    await _make_entry(db_session, t, amount=Decimal("200.00"), service_order_id=os_a.id)
    await _make_entry(db_session, t, amount=Decimal("500.00"), service_order_id=os_b.id)

    response = await http_client.get(
        "/api/v1/financial/summary",
        headers={**auth_headers(tec_a), "X-Tenant-ID": str(t.id)},
    )
    assert response.status_code == 200
    data = response.json()
    # tec_a deve ver apenas seus R$200, nunca os R$500 de tec_b
    assert float(data["total_receitas"]) == 200.0, (
        f"TECNICO deve ver apenas R$200 das suas OS, mas viu R${data['total_receitas']}"
    )


# ── 5. Isolamento entre tenants ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_nao_ve_lancamentos_de_outro_tenant(
    http_client: AsyncClient,
    db_session: AsyncSession,
):
    """ADMIN de tenant A não enxerga lançamentos do tenant B."""
    t_a = await _make_tenant(db_session)
    t_b = await _make_tenant(db_session)

    admin_a = await _make_user(db_session, t_a, UserRole.ADMIN)
    cli_b = await _make_client(db_session, t_b)
    os_b = await _make_os(db_session, t_b, cli_b, number=4001)
    entry_b = await _make_entry(db_session, t_b, service_order_id=os_b.id)

    response = await http_client.get(
        "/api/v1/financial",
        headers={**auth_headers(admin_a), "X-Tenant-ID": str(t_a.id)},
    )
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert str(entry_b.id) not in ids, "Lançamentos de outro tenant NÃO devem aparecer"
