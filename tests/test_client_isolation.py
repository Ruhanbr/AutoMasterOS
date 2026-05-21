"""
🔒 Client Isolation Tests — AutoMaster
======================================

Valida que CADA MÁQUINA pertence a EXATAMENTE 1 CLIENTE com ZERO VAZAMENTO.

Cenários obrigatórios (conforme spec):
  1. Cliente A cria máquina → 201 OK
  2. Cliente A lista  → vê sua máquina
  3. Cliente B lista  → [] vazio
  4. Cliente B acessa máquina do A → 403
  5. pytest → 100% verde

Cenários extras (defense-in-depth):
  6. Sem X-Cliente-ID (modo admin) → vê todas do tenant
  7. X-Cliente-ID inválido (UUID malformado) → 400
  8. X-Cliente-ID de cliente de outro tenant → 403
  9. Histórico OS: cliente B → 403
 10. Colheitadeira (tipo específico) isolada corretamente
"""

import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.client import Client, DocumentType
from app.models.machine import Machine
from app.models.tenant import Tenant
from app.models.user import User, UserRole


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures de setup: 2 clientes no mesmo tenant
# ─────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def cliente_a(db_session, tenant: Tenant) -> Client:
    c = Client(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Fazenda Bom Futuro",
        document="11111111000111",
        document_type=DocumentType.CNPJ,
        email="bom_futuro@fazenda.com",
        phone="64991110001",
        municipio="Rio Verde",
        uf="GO",
        cep="75901000",
        codigo_municipio="5218805",
        logradouro="Estrada Rural",
        numero="KM 12",
        bairro="Zona Rural",
        active=True,
    )
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def cliente_b(db_session, tenant: Tenant) -> Client:
    c = Client(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Agropecuária Cerrado",
        document="22222222000122",
        document_type=DocumentType.CNPJ,
        email="cerrado@agro.com",
        phone="64992220002",
        municipio="Jataí",
        uf="GO",
        cep="75800000",
        codigo_municipio="5211909",
        logradouro="Rod. GO-206",
        numero="KM 5",
        bairro="Zona Rural",
        active=True,
    )
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def colheitadeira_cliente_a(
    db_session, tenant: Tenant, cliente_a: Client
) -> Machine:
    """Colheitadeira pertencente EXCLUSIVAMENTE ao cliente A."""
    m = Machine(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        client_id=cliente_a.id,
        machine_type="Colheitadeiras",
        model="S680",
        brand="John Deere",
        serial_number=f"COLH-{uuid.uuid4().hex[:8].upper()}",
        year=2022,
        active=True,
    )
    db_session.add(m)
    await db_session.flush()
    return m


def _auth_headers(user: User) -> dict:
    from app.core.security import create_access_token

    token = create_access_token(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        role=UserRole(user.role).value,
    )
    return {"Authorization": f"Bearer {token}"}


def _cliente_header(client: Client) -> dict:
    return {"X-Cliente-ID": str(client.id)}


# ─────────────────────────────────────────────────────────────────────────────
# Cenário 1: Cliente A cria máquina → 201
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_1_cliente_a_cria_maquina(
    http_client: AsyncClient,
    user_admin: User,
    tenant: Tenant,
    cliente_a: Client,
):
    """Cliente A cria máquina → HTTP 201, client_id correto no response."""
    payload = {
        "client_id": str(cliente_a.id),
        "machine_type": "Colheitadeiras",
        "model": "S690",
        "brand": "John Deere",
        "serial_number": f"TEST-{uuid.uuid4().hex[:6].upper()}",
        "year": 2023,
    }
    resp = await http_client.post(
        "/api/v1/machines/",
        json=payload,
        headers={**_auth_headers(user_admin), **_cliente_header(cliente_a)},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["client_id"] == str(cliente_a.id)
    assert body["machine_type"] == "Colheitadeiras"


# ─────────────────────────────────────────────────────────────────────────────
# Cenário 2: Cliente A lista → vê sua colheitadeira
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_2_cliente_a_lista_ve_sua_maquina(
    http_client: AsyncClient,
    user_admin: User,
    cliente_a: Client,
    colheitadeira_cliente_a: Machine,
):
    """GET /machines/ com X-Cliente-ID: A → retorna a colheitadeira do A."""
    resp = await http_client.get(
        "/api/v1/machines/",
        headers={**_auth_headers(user_admin), **_cliente_header(cliente_a)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    ids = [item["id"] for item in body["items"]]
    assert str(colheitadeira_cliente_a.id) in ids
    # Todas as máquinas retornadas devem pertencer ao cliente A
    for item in body["items"]:
        assert item["client_id"] == str(cliente_a.id), (
            f"Vazamento: máquina {item['id']} pertence a outro cliente!"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Cenário 3: Cliente B lista → [] vazio (não vê máquinas do A)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_3_cliente_b_lista_ve_vazio(
    http_client: AsyncClient,
    user_admin: User,
    cliente_b: Client,
    colheitadeira_cliente_a: Machine,
):
    """GET /machines/ com X-Cliente-ID: B → lista vazia (B não tem máquinas)."""
    resp = await http_client.get(
        "/api/v1/machines/",
        headers={**_auth_headers(user_admin), **_cliente_header(cliente_b)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Cenário 4: Cliente B acessa máquina do A → 403
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_4_cliente_b_acessa_maquina_a_recebe_403(
    http_client: AsyncClient,
    user_admin: User,
    cliente_b: Client,
    colheitadeira_cliente_a: Machine,
):
    """GET /machines/{id} com X-Cliente-ID: B tentando acessar máquina do A → 403."""
    resp = await http_client.get(
        f"/api/v1/machines/{colheitadeira_cliente_a.id}",
        headers={**_auth_headers(user_admin), **_cliente_header(cliente_b)},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["code"] == "CLIENT_OWNERSHIP_VIOLATION"


# ─────────────────────────────────────────────────────────────────────────────
# Cenário 5 já é implícito: todos os 4 anteriores passando = 100% verde
# Cenário extra 6: sem X-Cliente-ID (modo admin) → vê todas do tenant
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_6_sem_header_admin_ve_todas_maquinas(
    http_client: AsyncClient,
    user_admin: User,
    colheitadeira_cliente_a: Machine,
):
    """SEM X-Cliente-ID → admin vê todas as máquinas do tenant (sem regressão)."""
    resp = await http_client.get(
        "/api/v1/machines/",
        headers=_auth_headers(user_admin),   # sem X-Cliente-ID
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert str(colheitadeira_cliente_a.id) in ids


@pytest.mark.asyncio
async def test_6b_sem_header_admin_acessa_qualquer_maquina(
    http_client: AsyncClient,
    user_admin: User,
    colheitadeira_cliente_a: Machine,
):
    """SEM X-Cliente-ID → admin pode acessar qualquer máquina do tenant."""
    resp = await http_client.get(
        f"/api/v1/machines/{colheitadeira_cliente_a.id}",
        headers=_auth_headers(user_admin),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == str(colheitadeira_cliente_a.id)


# ─────────────────────────────────────────────────────────────────────────────
# Cenário extra 7: UUID malformado → 400
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_7_header_uuid_invalido_retorna_400(
    http_client: AsyncClient,
    user_admin: User,
):
    """X-Cliente-ID com UUID malformado → HTTP 400."""
    resp = await http_client.get(
        "/api/v1/machines/",
        headers={**_auth_headers(user_admin), "X-Cliente-ID": "nao-e-um-uuid"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_HEADER"


# ─────────────────────────────────────────────────────────────────────────────
# Cenário extra 8: cliente de outro tenant → 403
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_8_cliente_outro_tenant_bloqueado(
    http_client: AsyncClient,
    db_session,
    user_admin: User,
    colheitadeira_cliente_a: Machine,
):
    """X-Cliente-ID de cliente que pertence a outro tenant → 403."""
    outro_tenant = Tenant(
        id=uuid.uuid4(),
        name="Outra Oficina",
        document="33333333000133",
        email="outra@oficina.com",
        razao_social="OUTRA OFICINA LTDA",
        municipio="Brasília",
        uf="DF",
        cep="70000000",
        codigo_municipio="5300108",
        logradouro="SIG",
        numero="1",
        bairro="Centro",
        crt="1",
        active=True,
    )
    db_session.add(outro_tenant)

    cliente_outro_tenant = Client(
        id=uuid.uuid4(),
        tenant_id=outro_tenant.id,
        name="Fazenda Remota",
        document="44444444000144",
        document_type=DocumentType.CNPJ,
        email="remota@fazenda.com",
        phone="61933330003",
        municipio="Brasília",
        uf="DF",
        cep="70000000",
        codigo_municipio="5300108",
        logradouro="SIG",
        numero="1",
        bairro="Centro",
        active=True,
    )
    db_session.add(cliente_outro_tenant)
    await db_session.flush()

    # Tenta usar o ID de um cliente de OUTRO tenant
    resp = await http_client.get(
        f"/api/v1/machines/{colheitadeira_cliente_a.id}",
        headers={
            **_auth_headers(user_admin),
            "X-Cliente-ID": str(cliente_outro_tenant.id),
        },
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Cenário extra 9: Histórico OS com X-Cliente-ID errado → 403
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_9_historico_os_cliente_errado_403(
    http_client: AsyncClient,
    user_admin: User,
    cliente_b: Client,
    colheitadeira_cliente_a: Machine,
):
    """GET /machines/{id}/os com X-Cliente-ID: B sobre máquina do A → 403."""
    resp = await http_client.get(
        f"/api/v1/machines/{colheitadeira_cliente_a.id}/os",
        headers={**_auth_headers(user_admin), **_cliente_header(cliente_b)},
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Cenário extra 10: tipo Colheitadeira especificamente isolado
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_10_colheitadeira_isolada_por_cliente(
    http_client: AsyncClient,
    user_admin: User,
    cliente_a: Client,
    cliente_b: Client,
    db_session,
    tenant: Tenant,
):
    """
    Colheitadeira criada para cliente A não aparece para cliente B.
    Reproduz exatamente o bug original reportado.
    """
    # Cria 1 colheitadeira para A e 1 trator para B
    from app.models.machine import Machine as MachineModel

    colh = MachineModel(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        client_id=cliente_a.id,
        machine_type="Colheitadeiras",
        model="CR9090",
        brand="New Holland",
        serial_number=f"NH-{uuid.uuid4().hex[:8].upper()}",
        year=2021,
        active=True,
    )
    db_session.add(colh)
    await db_session.flush()

    # Cliente A: vê a colheitadeira
    resp_a = await http_client.get(
        "/api/v1/machines/",
        headers={**_auth_headers(user_admin), **_cliente_header(cliente_a)},
    )
    assert resp_a.status_code == 200
    ids_a = [i["id"] for i in resp_a.json()["items"]]
    assert str(colh.id) in ids_a, "BUG: colheitadeira não aparece para o dono!"

    # Cliente B: NÃO vê a colheitadeira do A
    resp_b = await http_client.get(
        "/api/v1/machines/",
        headers={**_auth_headers(user_admin), **_cliente_header(cliente_b)},
    )
    assert resp_b.status_code == 200
    ids_b = [i["id"] for i in resp_b.json()["items"]]
    assert str(colh.id) not in ids_b, (
        "BUG CRÍTICO: colheitadeira do Cliente A apareceu para Cliente B!"
    )

    # Cliente B tenta acessar diretamente → 403
    resp_403 = await http_client.get(
        f"/api/v1/machines/{colh.id}",
        headers={**_auth_headers(user_admin), **_cliente_header(cliente_b)},
    )
    assert resp_403.status_code == 403, (
        "BUG CRÍTICO: Cliente B acessou colheitadeira do Cliente A sem 403!"
    )
