"""
Testes — OS Avançada (Phase E).

Cenários cobertos:
  UNIT
  1. test_calcular_totais_sem_itens              — OS vazia → subtotais zerados
  2. test_calcular_totais_so_servico             — apenas SERVICO
  3. test_calcular_totais_com_deslocamento       — SERVICO + DESLOCAMENTO + desconto
  4. test_calcular_totais_tipo_desconhecido      — tipo futuro cai em SERVICO
  5. test_subtotais_labels_omite_zeros           — subtotais_labels sem chaves zero

  INTEGRATION — GET /machines/{id}/os
  6. test_machine_os_endpoint_paginacao          — 25 OS, page=1&limit=10 → 10, page=3 → 5
  7. test_machine_os_endpoint_outra_maquina      — OS de outra máquina não aparece
  8. test_machine_os_endpoint_tenant_isolado     — tenant diferente → lista vazia
  9. test_machine_os_endpoint_machine_nao_existe — máquina inexistente → 404
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import create_access_token
from app.main import app
from app.core.security import hash_password
from app.models.client import Client, DocumentType
from app.models.machine import Machine
from app.models.service_order import ServiceOrder, ServiceOrderStatus
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.modules.reports.pdf_totals import calcular_totais_os

# asyncio_mode=auto handles async tests — pytestmark not needed here

# ── helpers ────────────────────────────────────────────────────────────────────

def _make_item(item_type: str, total_price: str):
    return SimpleNamespace(item_type=item_type, total_price=Decimal(total_price))


def _make_order(items: list, total_discount: str = "0.00"):
    return SimpleNamespace(items=items, total_discount=Decimal(total_discount))


def _auth_headers(user: User) -> dict:
    token = create_access_token(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        role=UserRole(user.role).value,
    )
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — calcular_totais_os
# ═══════════════════════════════════════════════════════════════════════════════

def test_calcular_totais_sem_itens():
    order = _make_order([])
    t = calcular_totais_os(order)
    assert t["total_bruto"] == Decimal("0.00")
    assert t["desconto"] == Decimal("0.00")
    assert t["total_final"] == Decimal("0.00")
    assert t["subtotais"]["SERVICO"] == Decimal("0.00")
    assert t["subtotais"]["PECA"] == Decimal("0.00")
    assert t["subtotais"]["DESLOCAMENTO"] == Decimal("0.00")


def test_calcular_totais_so_servico():
    items = [
        _make_item("SERVICO", "200.00"),
        _make_item("SERVICO", "150.00"),
    ]
    order = _make_order(items)
    t = calcular_totais_os(order)
    assert t["subtotais"]["SERVICO"] == Decimal("350.00")
    assert t["subtotais"]["PECA"] == Decimal("0.00")
    assert t["subtotais"]["DESLOCAMENTO"] == Decimal("0.00")
    assert t["total_bruto"] == Decimal("350.00")
    assert t["total_final"] == Decimal("350.00")
    # label presente
    assert "Serviço" in t["subtotais_labels"]
    assert "Peça" not in t["subtotais_labels"]
    assert "Deslocamento" not in t["subtotais_labels"]


def test_calcular_totais_com_deslocamento():
    items = [
        _make_item("SERVICO", "400.00"),
        _make_item("PECA", "100.00"),
        _make_item("DESLOCAMENTO", "50.00"),
    ]
    order = _make_order(items, total_discount="25.00")
    t = calcular_totais_os(order)
    assert t["subtotais"]["SERVICO"] == Decimal("400.00")
    assert t["subtotais"]["PECA"] == Decimal("100.00")
    assert t["subtotais"]["DESLOCAMENTO"] == Decimal("50.00")
    assert t["total_bruto"] == Decimal("550.00")
    assert t["desconto"] == Decimal("25.00")
    assert t["total_final"] == Decimal("525.00")
    # invariante fundamental
    assert t["total_final"] == t["total_bruto"] - t["desconto"]
    # todos os labels presentes
    assert "Serviço" in t["subtotais_labels"]
    assert "Peça" in t["subtotais_labels"]
    assert "Deslocamento" in t["subtotais_labels"]


def test_calcular_totais_tipo_desconhecido():
    """Tipos não mapeados (ex.: futuras expansões) caem em SERVICO por segurança."""
    items = [_make_item("INSPECAO", "80.00")]
    order = _make_order(items)
    t = calcular_totais_os(order)
    assert t["subtotais"]["SERVICO"] == Decimal("80.00")
    assert t["total_final"] == Decimal("80.00")


def test_subtotais_labels_omite_zeros():
    items = [_make_item("PECA", "120.00")]
    order = _make_order(items)
    t = calcular_totais_os(order)
    # Serviço e Deslocamento são zero → não devem aparecer
    assert "Serviço" not in t["subtotais_labels"]
    assert "Deslocamento" not in t["subtotais_labels"]
    assert t["subtotais_labels"]["Peça"] == Decimal("120.00")


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS — GET /machines/{id}/os
# ═══════════════════════════════════════════════════════════════════════════════

# ── fixtures locais ────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def _tenant_b(db_session: AsyncSession) -> Tenant:
    """Segundo tenant para teste de isolamento."""
    t = Tenant(
        id=uuid.uuid4(),
        name="Oficina B",
        document="99888777000166",
        email="b@oficina.com",
        razao_social="OFICINA B LTDA",
        nome_fantasia="Oficina B",
        inscricao_estadual="999888777666",
        municipio="Curitiba",
        uf="PR",
        cep="80010100",
        codigo_municipio="4106902",
        logradouro="Rua XV de Novembro",
        numero="1",
        bairro="Centro",
        crt="1",
        active=True,
    )
    db_session.add(t)
    await db_session.flush()
    return t


def _so(tenant_id, client_id, machine_id, number: int) -> ServiceOrder:
    return ServiceOrder(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        client_id=client_id,
        machine_id=machine_id,
        number=number,
        status=ServiceOrderStatus.ABERTA,
        opened_at=datetime.now(timezone.utc),
        total_services=Decimal("0.00"),
        total_parts=Decimal("0.00"),
        total_displacement=Decimal("0.00"),
        total_discount=Decimal("0.00"),
        total_amount=Decimal("0.00"),
    )


@pytest_asyncio.fixture
async def _machine_os_setup(
    db_session: AsyncSession,
    tenant: Tenant,
    client_entity: Client,
    machine: Machine,
    user_admin: User,
    _tenant_b: Tenant,
) -> dict:
    """
    Cria 25 OS para `machine` + 3 OS para outra máquina do mesmo tenant
    + 2 OS do tenant B (isolamento).
    """
    # Outra máquina — mesmo tenant, mesmo cliente
    other_machine = Machine(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        client_id=client_entity.id,
        machine_type="Colheitadeira",
        model="S680",
        brand="John Deere",
        serial_number=f"JD-OTHER-{uuid.uuid4().hex[:6].upper()}",
        year=2022,
        active=True,
    )
    db_session.add(other_machine)

    # Cliente do tenant B
    client_b = Client(
        id=uuid.uuid4(),
        tenant_id=_tenant_b.id,
        name="Fazenda B",
        document="98765432100",
        document_type=DocumentType.CPF,
        email="b@fazenda.com",
        phone="41999990000",
        municipio="Curitiba",
        uf="PR",
        cep="80010100",
        codigo_municipio="4106902",
        logradouro="Rua XV",
        numero="1",
        bairro="Centro",
        active=True,
    )
    db_session.add(client_b)

    # Máquina do tenant B
    machine_b = Machine(
        id=uuid.uuid4(),
        tenant_id=_tenant_b.id,
        client_id=client_b.id,
        machine_type="Trator",
        model="7090",
        brand="Valtra",
        serial_number=f"V-{uuid.uuid4().hex[:8].upper()}",
        year=2021,
        active=True,
    )
    db_session.add(machine_b)

    await db_session.flush()

    # 25 OS para a máquina principal
    os_list = [_so(tenant.id, client_entity.id, machine.id, n) for n in range(1, 26)]
    # 3 OS para outra máquina do mesmo tenant
    os_list += [_so(tenant.id, client_entity.id, other_machine.id, n) for n in range(26, 29)]
    # 2 OS do tenant B
    os_list += [_so(_tenant_b.id, client_b.id, machine_b.id, n) for n in range(1, 3)]

    db_session.add_all(os_list)
    await db_session.flush()

    # Admin user for tenant B (needed for auth token)
    user_b = User(
        id=uuid.uuid4(),
        tenant_id=_tenant_b.id,
        email="admin@oficinab.com",
        hashed_password=hash_password("senha123456"),
        full_name="Admin B",
        role=UserRole.ADMIN,
        active=True,
    )
    db_session.add(user_b)
    await db_session.flush()

    return {
        "machine_id": machine.id,
        "other_machine_id": other_machine.id,
        "tenant": tenant,
        "tenant_b": _tenant_b,
        "user": user_admin,
        "user_b": user_b,
    }


@pytest_asyncio.fixture
async def _api(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override():
        yield db_session

    app.dependency_overrides[get_db_session] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test/api/v1",
        follow_redirects=True,
    ) as client:
        yield client
    app.dependency_overrides.clear()


# ── testes de integração ───────────────────────────────────────────────────────

async def test_machine_os_endpoint_paginacao(_api: AsyncClient, _machine_os_setup: dict):
    setup = _machine_os_setup
    headers = _auth_headers(setup["user"])
    machine_id = setup["machine_id"]

    # Página 1 — 10 itens
    r1 = await _api.get(
        f"/machines/{machine_id}/os",
        params={"page": 1, "page_size": 10},
        headers=headers,
    )
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["total"] == 25
    assert len(body1["items"]) == 10
    assert body1["pages"] == 3

    # Página 3 — 5 itens restantes
    r3 = await _api.get(
        f"/machines/{machine_id}/os",
        params={"page": 3, "page_size": 10},
        headers=headers,
    )
    assert r3.status_code == 200
    body3 = r3.json()
    assert len(body3["items"]) == 5

    # Nenhum item de outra máquina deve aparecer
    all_ids_page1 = {item["id"] for item in body1["items"]}
    all_ids_page3 = {item["id"] for item in body3["items"]}
    assert len(all_ids_page1 | all_ids_page3) == 15  # 10 + 5


async def test_machine_os_endpoint_outra_maquina(_api: AsyncClient, _machine_os_setup: dict):
    """OS da outra máquina não aparecem na listagem da máquina principal."""
    setup = _machine_os_setup
    headers = _auth_headers(setup["user"])

    # Busca OS da máquina principal com page_size grande
    r = await _api.get(
        f"/machines/{setup['machine_id']}/os",
        params={"page": 1, "page_size": 100},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    # total deve ser exatamente 25 (não 28)
    assert body["total"] == 25


async def test_machine_os_endpoint_tenant_isolado(_api: AsyncClient, _machine_os_setup: dict):
    """
    Usuário do tenant B tenta listar OS de uma máquina do tenant A → 404.
    O endpoint bloqueia via MachineService.get() que filtra por tenant.
    """
    setup = _machine_os_setup
    # user_b is a real DB user for tenant B created in the setup fixture
    headers_b = _auth_headers(setup["user_b"])

    r = await _api.get(
        f"/machines/{setup['machine_id']}/os",
        params={"page": 1, "page_size": 10},
        headers=headers_b,
    )
    # Máquina pertence ao tenant A — tenant B não pode vê-la
    assert r.status_code == 404


async def test_machine_os_endpoint_machine_nao_existe(_api: AsyncClient, _machine_os_setup: dict):
    headers = _auth_headers(_machine_os_setup["user"])
    fake_id = uuid.uuid4()
    r = await _api.get(f"/machines/{fake_id}/os", headers=headers)
    assert r.status_code == 404
