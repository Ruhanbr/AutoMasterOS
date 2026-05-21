"""
FAANG Feature Tests — AutoMaster

Cobre:
  1. Histórico OS máquina (paginado + selectinload, N+1 free)
  2. Cache Redis financeiro (hit/miss/invalidação)
  3. PDF totais explícitos (valores reais no bytes gerado)
  4. Assinatura técnico no PDF (seção presente)
  5. Middleware trace_id (header X-Trace-ID)
  6. /ready endpoint (health checks)
"""

import io
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.service_order import ItemType, ServiceOrder, ServiceOrderItem, ServiceOrderStatus
from app.modules.reports.os_pdf import generate_os_pdf


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures locais
# ─────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def multiple_orders(
    db_session,
    tenant,
    client_entity,
    machine,
) -> list[ServiceOrder]:
    """Cria 5 OS para a máquina — usado nos testes de histórico."""
    orders = []
    for i in range(5):
        so = ServiceOrder(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            client_id=client_entity.id,
            machine_id=machine.id,
            number=100 + i,
            status=ServiceOrderStatus.ABERTA,
            description=f"OS de teste #{i}",
            opened_at=datetime.now(timezone.utc),
            total_services=Decimal("200.00"),
            total_parts=Decimal("50.00"),
            total_displacement=Decimal("0.00"),
            total_discount=Decimal("0.00"),
            total_amount=Decimal("250.00"),
        )
        db_session.add(so)
        orders.append(so)

    await db_session.flush()

    # Adiciona itens à primeira OS para testar selectinload
    item = ServiceOrderItem(
        id=uuid.uuid4(),
        service_order_id=orders[0].id,
        item_type=ItemType.SERVICO,
        description="Troca de correia",
        quantity=Decimal("1.000"),
        unit_price=Decimal("200.00"),
        discount=Decimal("0.00"),
        total_price=Decimal("200.00"),
    )
    db_session.add(item)
    await db_session.flush()
    return orders


# ─────────────────────────────────────────────────────────────────────────────
# 1. Histórico OS — selectinload + paginação
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_historico_os_paginado_retorna_dados(
    http_client: AsyncClient,
    user_admin,
    tenant,
    machine,
    multiple_orders,
):
    """GET /machines/{id}/os deve retornar lista paginada com estrutura correta."""
    from tests.conftest import auth_headers

    resp = await http_client.get(
        f"/api/v1/machines/{machine.id}/os?page=1&page_size=3",
        headers=auth_headers(user_admin),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 3
    assert body["page"] == 1
    assert body["pages"] == 2


@pytest.mark.asyncio
async def test_historico_os_pagina_2(
    http_client: AsyncClient,
    user_admin,
    tenant,
    machine,
    multiple_orders,
):
    """Página 2 deve retornar os 2 registros restantes."""
    from tests.conftest import auth_headers

    resp = await http_client.get(
        f"/api/v1/machines/{machine.id}/os?page=2&page_size=3",
        headers=auth_headers(user_admin),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["page"] == 2


@pytest.mark.asyncio
async def test_historico_os_isolamento_tenant(
    http_client: AsyncClient,
    db_session,
    tenant,
    machine,
    multiple_orders,
):
    """Tenant diferente NÃO pode acessar máquina de outro tenant."""
    from app.models.tenant import Tenant
    from app.models.user import User, UserRole
    from app.core.security import hash_password
    from tests.conftest import auth_headers

    # Cria tenant + user externos
    outro_tenant = Tenant(
        id=uuid.uuid4(),
        name="Outra Oficina",
        document="98765432000199",
        email="outro@oficina.com",
        razao_social="OUTRA OFICINA LTDA",
        municipio="Curitiba",
        uf="PR",
        cep="80000000",
        codigo_municipio="4106902",
        logradouro="Rua das Araucárias",
        numero="99",
        bairro="Centro",
        crt="1",
        active=True,
    )
    db_session.add(outro_tenant)
    await db_session.flush()

    outro_user = User(
        id=uuid.uuid4(),
        tenant_id=outro_tenant.id,
        email="admin@outra.com",
        hashed_password=hash_password("senha123456"),
        full_name="Outro Admin",
        role=UserRole.ADMIN,
        active=True,
    )
    db_session.add(outro_user)
    await db_session.flush()

    resp = await http_client.get(
        f"/api/v1/machines/{machine.id}/os",
        headers=auth_headers(outro_user),
    )
    # Máquina não existe no contexto do outro tenant → 404
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_historico_os_selectinload_performance(
    http_client: AsyncClient,
    user_admin,
    machine,
    multiple_orders,
):
    """Endpoint deve responder em < 500 ms mesmo com múltiplas OS + itens."""
    from tests.conftest import auth_headers

    start = time.perf_counter()
    resp = await http_client.get(
        f"/api/v1/machines/{machine.id}/os",
        headers=auth_headers(user_admin),
    )
    duration = time.perf_counter() - start

    assert resp.status_code == 200
    assert duration < 0.5, f"Resposta lenta: {duration:.3f}s (esperado < 0.5s)"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cache Redis — financial summary hit/miss
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_financial_summary_cache_miss_then_hit(
    http_client: AsyncClient,
    user_admin,
    tenant,
):
    """Duas chamadas idênticas ao summary devem retornar os mesmos dados."""
    from tests.conftest import auth_headers

    headers = auth_headers(user_admin)

    resp1 = await http_client.get("/api/v1/financial/summary", headers=headers)
    resp2 = await http_client.get("/api/v1/financial/summary", headers=headers)

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()


@pytest.mark.asyncio
async def test_financial_summary_cache_invalidado_apos_despesa(
    http_client: AsyncClient,
    user_admin,
    tenant,
):
    """Registrar despesa deve invalidar o cache e retornar valores atualizados."""
    from tests.conftest import auth_headers

    headers = auth_headers(user_admin)

    resp_antes = await http_client.get("/api/v1/financial/summary", headers=headers)
    assert resp_antes.status_code == 200
    saldo_antes = Decimal(str(resp_antes.json()["saldo"]))

    expense = {
        "amount": "100.00",
        "description": "Compra de ferramentas",
        "category": "Equipamentos",
        "reference_date": datetime.now(timezone.utc).isoformat(),
    }
    resp_post = await http_client.post(
        "/api/v1/financial/expenses", json=expense, headers=headers
    )
    assert resp_post.status_code == 201

    resp_depois = await http_client.get("/api/v1/financial/summary", headers=headers)
    assert resp_depois.status_code == 200
    saldo_depois = Decimal(str(resp_depois.json()["saldo"]))

    # Saldo deve ter diminuído em R$ 100 após registrar despesa
    assert saldo_depois == saldo_antes - Decimal("100.00")


# ─────────────────────────────────────────────────────────────────────────────
# 3. PDF — totais explícitos e seção de assinatura
# ─────────────────────────────────────────────────────────────────────────────

def _build_order_data(
    total_services="350.00",
    total_parts="90.00",
    total_displacement="50.00",
    total_discount="10.00",
    total_amount="480.00",
    signature_url=None,
):
    return {
        "os_number": 42,
        "status": "FINALIZADA",
        "opened_at": datetime(2026, 1, 10, 8, 0),
        "finished_at": datetime(2026, 1, 12, 17, 0),
        "technician_name": "João Técnico",
        "technician_signature_url": signature_url,
        "description": "Revisão anual",
        "diagnosis": "Motor com folga",
        "solution": "Ajuste e troca de peças",
        "client_name": "Fazenda Progresso",
        "client_document": "12.345.678/0001-90",
        "client_phone": "(64) 99999-1234",
        "machine_model": "7200",
        "machine_brand": "John Deere",
        "machine_serial": "JD-2020-001",
        "items": [
            {"item_type": "SERVICO", "description": "Revisão motor", "quantity": 1, "unit_price": Decimal("350.00"), "total_price": Decimal("350.00")},
            {"item_type": "PECA", "description": "Filtro de óleo", "quantity": 2, "unit_price": Decimal("45.00"), "total_price": Decimal("90.00")},
            {"item_type": "DESLOCAMENTO", "description": "Deslocamento fazenda", "quantity": 1, "unit_price": Decimal("50.00"), "total_price": Decimal("50.00")},
        ],
        "total_services": Decimal(total_services),
        "total_parts": Decimal(total_parts),
        "total_displacement": Decimal(total_displacement),
        "total_discount": Decimal(total_discount),
        "total_amount": Decimal(total_amount),
        "tenant_name": "AutoMaster Teste",
        "generated_at": datetime(2026, 1, 12, 18, 0),
    }


def test_pdf_gerado_e_nao_vazio():
    """PDF deve ser gerado como bytes não vazios."""
    pdf = generate_os_pdf(_build_order_data())
    assert isinstance(pdf, bytes)
    assert len(pdf) > 1024  # PDF mínimo real


def test_pdf_contem_subtotal_servicos():
    """PDF deve conter a string 'Subtotal Serviços' com o valor correto."""
    from pdfminer.high_level import extract_text  # type: ignore

    pdf = generate_os_pdf(_build_order_data())
    text = extract_text(io.BytesIO(pdf))
    assert "Subtotal Serviços" in text
    assert "350" in text


def test_pdf_contem_subtotal_pecas():
    """PDF deve conter subtotal de peças."""
    from pdfminer.high_level import extract_text

    pdf = generate_os_pdf(_build_order_data())
    text = extract_text(io.BytesIO(pdf))
    assert "Subtotal Peças" in text
    assert "90" in text


def test_pdf_contem_subtotal_deslocamento():
    """Deslocamento > 0 deve aparecer no PDF."""
    from pdfminer.high_level import extract_text

    pdf = generate_os_pdf(_build_order_data())
    text = extract_text(io.BytesIO(pdf))
    assert "Subtotal Deslocamento" in text
    assert "50" in text


def test_pdf_contem_total_final():
    """Linha TOTAL deve aparecer com valor correto."""
    from pdfminer.high_level import extract_text

    pdf = generate_os_pdf(_build_order_data())
    text = extract_text(io.BytesIO(pdf))
    assert "TOTAL" in text
    assert "480" in text


def test_pdf_contem_secao_tecnico_responsavel_sem_imagem():
    """Sem assinatura_url, PDF deve conter 'Assinatura do Técnico'."""
    from pdfminer.high_level import extract_text

    pdf = generate_os_pdf(_build_order_data(signature_url=None))
    text = extract_text(io.BytesIO(pdf))
    assert "Assinatura do Técnico" in text


def test_pdf_contem_tecnico_responsavel_com_imagem(tmp_path):
    """Com assinatura_url válido, PDF deve conter 'Técnico Responsável'."""
    from pdfminer.high_level import extract_text
    from PIL import Image as PILImage

    # Cria imagem PNG de teste
    sig_path = str(tmp_path / "assinatura.png")
    img = PILImage.new("RGB", (200, 80), color=(255, 255, 255))
    img.save(sig_path)

    pdf = generate_os_pdf(_build_order_data(signature_url=sig_path))
    text = extract_text(io.BytesIO(pdf))
    assert "Técnico Responsável" in text


def test_pdf_sem_deslocamento_nao_mostra_linha():
    """Se deslocamento = 0 a linha não deve aparecer."""
    from pdfminer.high_level import extract_text

    data = _build_order_data(total_displacement="0.00", total_amount="430.00")
    pdf = generate_os_pdf(data)
    text = extract_text(io.BytesIO(pdf))
    assert "Subtotal Deslocamento" not in text


# ─────────────────────────────────────────────────────────────────────────────
# 4. Trace ID — middleware injeta X-Trace-ID no response
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trace_id_presente_no_response_header(http_client: AsyncClient):
    """Toda resposta deve ter o header X-Trace-ID com UUID v4."""
    resp = await http_client.get("/health")
    assert resp.status_code == 200
    tid = resp.headers.get("X-Trace-ID")
    assert tid is not None
    # Valida formato UUID
    parsed = uuid.UUID(tid)
    assert parsed.version == 4


@pytest.mark.asyncio
async def test_trace_id_diferente_por_request(http_client: AsyncClient):
    """Cada requisição deve gerar um trace_id único."""
    resp1 = await http_client.get("/health")
    resp2 = await http_client.get("/health")
    tid1 = resp1.headers["X-Trace-ID"]
    tid2 = resp2.headers["X-Trace-ID"]
    assert tid1 != tid2


# ─────────────────────────────────────────────────────────────────────────────
# 5. /ready — health checks
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ready_retorna_status_estruturado(http_client: AsyncClient):
    """/ready deve retornar JSON com 'status' e 'checks'."""
    resp = await http_client.get("/ready")
    # Pode ser 200 ou 503 dependendo do ambiente — mas estrutura deve ser válida
    body = resp.json()
    assert "status" in body
    assert "checks" in body
    assert "database" in body["checks"]
    assert "redis" in body["checks"]


@pytest.mark.asyncio
async def test_health_ok(http_client: AsyncClient):
    """/health sempre deve retornar 200."""
    resp = await http_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Redis cache client — unit tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_set_get_delete():
    """CacheClient deve serializar, recuperar e deletar valores JSON."""
    from app.core.redis_client import CacheClient

    client = CacheClient()

    # Mock do Redis para não precisar de Redis real nos testes unitários
    mock_redis = AsyncMock()
    raw_json = '{"foo": "bar", "n": 42}'
    mock_redis.get.return_value = raw_json
    mock_redis.setex = AsyncMock()
    mock_redis.delete = AsyncMock()
    client._client = mock_redis

    # SET
    await client.set("test:key", {"foo": "bar", "n": 42}, ttl=60)
    mock_redis.setex.assert_called_once()

    # GET
    result = await client.get("test:key")
    assert result == {"foo": "bar", "n": 42}

    # DELETE
    await client.delete("test:key")
    mock_redis.delete.assert_called_once_with("test:key")


@pytest.mark.asyncio
async def test_cache_get_retorna_none_em_falha():
    """Falha no Redis não deve propagar exceção — deve retornar None."""
    from app.core.redis_client import CacheClient

    client = CacheClient()
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = ConnectionError("Redis down")
    client._client = mock_redis

    result = await client.get("any:key")
    assert result is None


@pytest.mark.asyncio
async def test_cache_delete_pattern():
    """delete_pattern deve iterar via SCAN e deletar chaves correspondentes."""
    from app.core.redis_client import CacheClient

    client = CacheClient()
    mock_redis = AsyncMock()

    async def fake_scan_iter(pattern, count):
        for k in [b"machine_os:t1:m1:1:10", b"machine_os:t1:m1:2:10"]:
            yield k

    mock_redis.scan_iter = fake_scan_iter
    mock_redis.delete = AsyncMock()
    client._client = mock_redis

    deleted = await client.delete_pattern("machine_os:t1:m1:*")
    assert deleted == 2
    assert mock_redis.delete.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# 7. MachineService.list_os_historico_cached — unit (mock Redis)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_machine_service_cache_hit_nao_chama_banco(db_session, tenant, machine):
    """Se cache hit, o repositório NÃO deve ser consultado."""
    from app.services.machine_service import MachineService

    svc = MachineService(db_session)

    cached_payload = {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 10,
        "pages": 1,
    }

    with patch("app.services.machine_service.cache") as mock_cache:
        mock_cache.get = AsyncMock(return_value=cached_payload)
        mock_cache.set = AsyncMock()

        result = await svc.list_os_historico_cached(
            tenant_id=tenant.id,
            machine_id=machine.id,
            page=1,
            page_size=10,
        )

    assert result.total == 0
    mock_cache.get.assert_called_once()
    # set NÃO deve ser chamado em cache hit
    mock_cache.set.assert_not_called()


@pytest.mark.asyncio
async def test_machine_service_cache_miss_popula_cache(
    db_session, tenant, machine, multiple_orders
):
    """Cache miss deve consultar banco e popular o cache."""
    from app.services.machine_service import MachineService

    svc = MachineService(db_session)

    with patch("app.services.machine_service.cache") as mock_cache:
        mock_cache.get = AsyncMock(return_value=None)   # miss
        mock_cache.set = AsyncMock()

        result = await svc.list_os_historico_cached(
            tenant_id=tenant.id,
            machine_id=machine.id,
            page=1,
            page_size=20,
        )

    assert result.total == 5
    mock_cache.set.assert_called_once()
    key_used = mock_cache.set.call_args[0][0]
    assert str(machine.id) in key_used
