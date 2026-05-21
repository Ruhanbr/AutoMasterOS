"""
Teste Ponta a Ponta (E2E) — AutoMaster.

Fluxo completo:
  1. Criar Tenant (oficina)
  2. Criar Cliente (produtor rural)
  3. Criar Máquina
  4. Criar Ordem de Serviço com itens
  5. Avançar status: ABERTA → EM_ANDAMENTO
  6. Finalizar OS (dispara NF-e via Celery)
  7. Executar NfeProcessor diretamente (bypass Celery, mock SEFAZ)
  8. Verificar: NF-e AUTORIZADA, XML gerado, DANFE gerado, dados consistentes

Variações adicionais:
  - Mock SEFAZ rejeição: NF-e REJEITADA, OS permanece FINALIZADA
  - Mock SEFAZ erro de comunicação: NF-e ERRO, retry_count incrementado
"""

import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from app.models.invoice import InvoiceStatus
from app.models.service_order import ItemType, ServiceOrderStatus
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.service_order_repository import ServiceOrderRepository
from app.schemas.client import ClientCreate
from app.schemas.machine import MachineCreate
from app.schemas.service_order import ServiceOrderCreate, ServiceOrderItemCreate
from app.schemas.tenant import TenantCreate
from app.services.client_service import ClientService
from app.services.machine_service import MachineService
from app.services.service_order_service import ServiceOrderService
from app.utils.sefaz_client import SefazMockClient, SefazRejectionError

pytestmark = pytest.mark.e2e


# ─── Fixtures E2E ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def e2e_tenant(db_session):
    from app.models.tenant import Tenant

    # Documento único por teste: NfeProcessor._run() comita a sessão,
    # tornando os dados permanentes; sem unicidade ocorre UniqueViolationError
    # nas fixtures dos testes seguintes na mesma sessão pytest.
    unique_doc = f"{uuid.uuid4().int % 10**14:014d}"
    t = Tenant(
        id=uuid.uuid4(),
        name="Oficina E2E",
        document=unique_doc,
        email=f"e2e-{uuid.uuid4().hex[:8]}@automaster.com",
        razao_social="OFICINA E2E SERVICOS AGRICOLAS LTDA",
        nome_fantasia="Oficina E2E",
        inscricao_estadual="111222333444",
        municipio="Ribeirão Preto",
        uf="SP",
        cep="14015020",
        codigo_municipio="3543402",
        logradouro="Rua do Campo",
        numero="500",
        bairro="Zona Rural",
        crt="1",
        active=True,
    )
    db_session.add(t)
    await db_session.flush()
    return t


@pytest_asyncio.fixture
async def e2e_client(db_session, e2e_tenant):
    from app.models.client import Client, DocumentType

    unique_doc = f"{uuid.uuid4().int % 10**14:014d}"
    c = Client(
        id=uuid.uuid4(),
        tenant_id=e2e_tenant.id,
        name="Fazenda Santa Fé",
        document=unique_doc,
        document_type=DocumentType.CNPJ,
        email="santafe@fazenda.com",
        phone="16999880000",
        municipio="Ribeirão Preto",
        uf="SP",
        cep="14075000",
        codigo_municipio="3543402",
        logradouro="Rodovia Anhanguera",
        numero="km 318",
        bairro="Rural",
        active=True,
    )
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def e2e_machine(db_session, e2e_tenant, e2e_client):
    from app.models.machine import Machine

    m = Machine(
        id=uuid.uuid4(),
        tenant_id=e2e_tenant.id,
        client_id=e2e_client.id,
        machine_type="Trator",
        model="8295R",
        brand="John Deere",
        serial_number=f"JD8295-{uuid.uuid4().hex[:6].upper()}",
        year=2021,
        horsepower="295 cv",
        active=True,
    )
    db_session.add(m)
    await db_session.flush()
    return m


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _create_and_prepare_order(db_session, e2e_tenant, e2e_client, e2e_machine):
    """Cria OS com itens e avança para EM_ANDAMENTO."""
    svc = ServiceOrderService(db_session)

    order = await svc.create(
        e2e_tenant.id,
        ServiceOrderCreate(
            client_id=e2e_client.id,
            machine_id=e2e_machine.id,
            description="Revisão completa 500h",
            technician_name="Carlos Mecânico",
            items=[
                ServiceOrderItemCreate(
                    item_type=ItemType.SERVICO,
                    description="Revisão completa 500 horas",
                    quantity=Decimal("1.000"),
                    unit_price=Decimal("480.00"),
                ),
                ServiceOrderItemCreate(
                    item_type=ItemType.PECA,
                    description="Filtro de óleo hidráulico",
                    ncm_code="84212300",
                    part_number="AH128404",
                    quantity=Decimal("2.000"),
                    unit_price=Decimal("87.50"),
                ),
                ServiceOrderItemCreate(
                    item_type=ItemType.PECA,
                    description="Óleo hidráulico John Deere HY-GARD 20L",
                    ncm_code="27101999",
                    quantity=Decimal("4.000"),
                    unit_price=Decimal("195.00"),
                ),
            ],
        ),
    )

    await svc.update_status(
        e2e_tenant.id, order.id, ServiceOrderStatus.EM_ANDAMENTO
    )
    return order


# ─── Testes E2E ───────────────────────────────────────────────────────────────

class TestFluxoCompletoAutorizacao:
    """
    Cenário feliz: OS finalizada → NF-e processada → AUTORIZADA.
    """

    async def test_fluxo_completo_nfe_autorizada(
        self, db_session, e2e_tenant, e2e_client, e2e_machine, tmp_path, monkeypatch
    ):
        # Redireciona storage para diretório temporário
        monkeypatch.setattr("app.core.config.settings.XML_OUTPUT_PATH", str(tmp_path / "xml"))
        monkeypatch.setattr("app.core.config.settings.DANFE_OUTPUT_PATH", str(tmp_path / "danfe"))
        monkeypatch.setattr("app.core.config.settings.SEFAZ_MOCK_ENABLED", True)

        # ── 1. Criar e preparar OS ─────────────────────────────────────────
        order = await _create_and_prepare_order(
            db_session, e2e_tenant, e2e_client, e2e_machine
        )
        assert order.status == ServiceOrderStatus.EM_ANDAMENTO

        # ── 2. Finalizar OS (mock Celery) ──────────────────────────────────
        with patch("app.workers.tasks.process_invoice_task") as mock_task:
            mock_task.apply_async = MagicMock()
            finalized = await ServiceOrderService(db_session).finalize(
                e2e_tenant.id, order.id, notes="Revisão concluída sem pendências"
            )

        assert finalized.status == ServiceOrderStatus.FINALIZADA
        assert finalized.finished_at is not None
        mock_task.apply_async.assert_called_once()

        # ── 3. Verificar Invoice criada (PENDENTE) ─────────────────────────
        invoice_repo = InvoiceRepository(db_session)
        invoice = await invoice_repo.get_by_service_order_id(order.id)

        assert invoice is not None
        assert invoice.status == InvoiceStatus.PENDENTE
        assert invoice.tenant_id == e2e_tenant.id
        assert invoice.total_amount == finalized.total_amount

        # ── 4. Executar NfeProcessor diretamente (bypass Celery) ──────────
        from app.workers.nfe_processor import NfeProcessor

        processor = NfeProcessor()
        result = await processor._run(db_session, str(invoice.id), invoice.idempotency_key)

        # ── 5. Verificar resultado final ────────────────────────────────────
        assert result["status"] == "authorized"
        assert "access_key" in result
        assert len(result["access_key"]) == 44
        assert result["access_key"].isdigit()

        # ── 6. Verificar estado persistido no banco ─────────────────────────
        await db_session.refresh(invoice)
        assert invoice.status == InvoiceStatus.AUTORIZADA
        assert invoice.access_key is not None
        assert invoice.protocol_number is not None
        assert invoice.authorized_at is not None
        assert invoice.number is not None
        assert invoice.xml_content is not None
        assert invoice.tax_data is not None

        # ── 7. Verificar XML no disco ──────────────────────────────────────
        xml_file = Path(invoice.xml_path)
        assert xml_file.exists()
        xml_content = xml_file.read_text(encoding="utf-8")
        assert "NFe" in xml_content
        assert e2e_tenant.razao_social in xml_content or "OFICINA" in xml_content
        assert invoice.access_key in xml_content

        # ── 8. Verificar DANFE no disco ────────────────────────────────────
        danfe_file = Path(invoice.danfe_path)
        assert danfe_file.exists()
        assert danfe_file.stat().st_size > 1000  # PDF não vazio

        # ── 9. Verificar dados tributários ─────────────────────────────────
        tax = invoice.tax_data
        assert tax["regime"] == "Simples Nacional"
        assert Decimal(tax["valor_total_nf"]) > Decimal("0")
        assert Decimal(tax["valor_total_tributos"]) > Decimal("0")

        # ── 10. Total da OS bate com total da NF ───────────────────────────
        expected_total = Decimal("480.00") + (Decimal("87.50") * 2) + (Decimal("195.00") * 4)
        assert abs(Decimal(tax["valor_total_nf"]) - expected_total) < Decimal("0.02")

    async def test_invoice_nao_duplicada_em_retry(
        self, db_session, e2e_tenant, e2e_client, e2e_machine, monkeypatch
    ):
        """
        Idempotência: processar a mesma invoice_id duas vezes
        não deve criar uma segunda NF-e nem falhar.
        """
        monkeypatch.setattr("app.core.config.settings.SEFAZ_MOCK_ENABLED", True)
        monkeypatch.setattr("app.core.config.settings.XML_OUTPUT_PATH", "/tmp/xml_retry")
        monkeypatch.setattr("app.core.config.settings.DANFE_OUTPUT_PATH", "/tmp/danfe_retry")

        order = await _create_and_prepare_order(
            db_session, e2e_tenant, e2e_client, e2e_machine
        )
        with patch("app.workers.tasks.process_invoice_task") as mock_task:
            mock_task.apply_async = MagicMock()
            await ServiceOrderService(db_session).finalize(e2e_tenant.id, order.id)

        invoice = await InvoiceRepository(db_session).get_by_service_order_id(order.id)

        # Primeira execução → AUTORIZADA
        from app.workers.nfe_processor import NfeProcessor
        processor = NfeProcessor()
        r1 = await processor._run(db_session, str(invoice.id), invoice.idempotency_key)
        assert r1["status"] == "authorized"

        # Segunda execução com mesma idempotency_key → deve retornar "already_authorized"
        r2 = await processor._run(db_session, str(invoice.id), invoice.idempotency_key)
        assert r2["status"] in {"already_authorized", "skipped"}

        # Garantia final: ainda existe apenas UMA NF-e para a OS
        all_invoices_stmt = __import__("sqlalchemy").select(
            __import__("app.models.invoice", fromlist=["Invoice"]).Invoice
        ).where(
            __import__("app.models.invoice", fromlist=["Invoice"]).Invoice.service_order_id == order.id
        )
        result = await db_session.execute(all_invoices_stmt)
        invoices = result.scalars().all()
        assert len(invoices) == 1


class TestFluxoRejeicaoSEFAZ:
    """
    Cenário de rejeição: SEFAZ retorna erro de negócio → NF-e REJEITADA.
    """

    async def test_nfe_rejeitada_quando_sefaz_rejeita(
        self, db_session, e2e_tenant, e2e_client, e2e_machine, monkeypatch
    ):
        monkeypatch.setattr("app.core.config.settings.SEFAZ_MOCK_ENABLED", True)
        monkeypatch.setattr("app.core.config.settings.XML_OUTPUT_PATH", "/tmp/xml_rej")
        monkeypatch.setattr("app.core.config.settings.DANFE_OUTPUT_PATH", "/tmp/danfe_rej")

        order = await _create_and_prepare_order(
            db_session, e2e_tenant, e2e_client, e2e_machine
        )
        with patch("app.workers.tasks.process_invoice_task") as mock_task:
            mock_task.apply_async = MagicMock()
            await ServiceOrderService(db_session).finalize(e2e_tenant.id, order.id)

        invoice = await InvoiceRepository(db_session).get_by_service_order_id(order.id)

        # Configura mock para rejeição
        mock_sefaz = SefazMockClient()
        mock_sefaz.force_rejection = True
        mock_sefaz.rejection_code = "204"
        mock_sefaz.rejection_message = "Duplicidade de NF-e"

        from app.workers.nfe_processor import NfeProcessor

        with patch("app.workers.nfe_processor.get_sefaz_client", return_value=mock_sefaz):
            result = await NfeProcessor()._run(
                db_session, str(invoice.id), invoice.idempotency_key
            )

        assert result["status"] == "rejected"
        assert result["code"] == "204"

        await db_session.refresh(invoice)
        assert invoice.status == InvoiceStatus.REJEITADA
        assert invoice.rejection_code == "204"
        assert invoice.rejected_at is not None

        # OS permanece FINALIZADA mesmo com NF rejeitada
        so_repo = ServiceOrderRepository(db_session)
        order_reloaded = await so_repo.get_by_id_and_tenant(order.id, e2e_tenant.id)
        assert order_reloaded.status == ServiceOrderStatus.FINALIZADA


class TestFluxoErroComunicacao:
    """
    Cenário de erro de rede: NF-e vai para ERRO, retry_count incrementado.
    """

    async def test_nfe_vai_para_erro_em_falha_de_comunicacao(
        self, db_session, e2e_tenant, e2e_client, e2e_machine, monkeypatch
    ):
        monkeypatch.setattr("app.core.config.settings.SEFAZ_MOCK_ENABLED", True)
        monkeypatch.setattr("app.core.config.settings.XML_OUTPUT_PATH", "/tmp/xml_err")
        monkeypatch.setattr("app.core.config.settings.DANFE_OUTPUT_PATH", "/tmp/danfe_err")

        order = await _create_and_prepare_order(
            db_session, e2e_tenant, e2e_client, e2e_machine
        )
        with patch("app.workers.tasks.process_invoice_task") as mock_task:
            mock_task.apply_async = MagicMock()
            await ServiceOrderService(db_session).finalize(e2e_tenant.id, order.id)

        invoice = await InvoiceRepository(db_session).get_by_service_order_id(order.id)

        mock_sefaz = SefazMockClient()
        mock_sefaz.force_error = True

        from app.utils.sefaz_client import SefazCommunicationError
        from app.workers.nfe_processor import NfeProcessor

        with patch("app.workers.nfe_processor.get_sefaz_client", return_value=mock_sefaz):
            with pytest.raises(SefazCommunicationError):
                await NfeProcessor()._run(
                    db_session, str(invoice.id), invoice.idempotency_key
                )

        await db_session.refresh(invoice)
        assert invoice.status == InvoiceStatus.ERRO
        assert invoice.last_error is not None
        assert invoice.next_retry_at is not None
        assert invoice.retry_count >= 1


class TestApiEndpointsE2E:
    """
    Testa os endpoints REST do fluxo completo.
    """

    async def test_fluxo_api_criar_os_e_finalizar(
        self, http_client, db_session, tenant, client_entity, machine, user_admin
    ):
        from tests.conftest import auth_headers
        headers = auth_headers(user_admin)

        # Criar OS
        resp = await http_client.post(
            "/api/v1/service-orders",
            json={
                "client_id": str(client_entity.id),
                "machine_id": str(machine.id),
                "description": "Revisão via API",
                "items": [
                    {
                        "item_type": "SERVICO",
                        "description": "Diagnóstico eletrônico",
                        "quantity": "1.000",
                        "unit_price": "250.00",
                    }
                ],
            },
            headers=headers,
        )
        assert resp.status_code == 201
        order_data = resp.json()
        order_id = order_data["id"]
        assert order_data["status"] == "ABERTA"

        # Avançar para EM_ANDAMENTO
        resp = await http_client.patch(
            f"/api/v1/service-orders/{order_id}/status",
            json={"status": "EM_ANDAMENTO"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "EM_ANDAMENTO"

        # Finalizar (mock Celery)
        with patch("app.workers.tasks.process_invoice_task") as mock_task:
            mock_task.apply_async = MagicMock()
            resp = await http_client.post(
                f"/api/v1/service-orders/{order_id}/finalize",
                headers=headers,
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "FINALIZADA"
        mock_task.apply_async.assert_called_once()

        # Consultar NF-e criada
        resp = await http_client.get(
            f"/api/v1/invoices/service-order/{order_id}",
            headers=headers,
        )
        assert resp.status_code == 200
        invoice_data = resp.json()
        assert invoice_data["status"] == "PENDENTE"
        assert invoice_data["service_order_id"] == order_id

    async def test_health_check(self, http_client):
        resp = await http_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_token_invalido_retorna_401(self, http_client):
        resp = await http_client.get(
            "/api/v1/clients",
            headers={"Authorization": "Bearer token.invalido.assinatura"},
        )
        assert resp.status_code == 401

    async def test_sem_token_retorna_401(self, http_client):
        resp = await http_client.get("/api/v1/clients")
        assert resp.status_code == 401

    async def test_os_nao_encontrada_retorna_404(self, http_client, user_admin):
        from tests.conftest import auth_headers
        resp = await http_client.get(
            f"/api/v1/service-orders/{uuid.uuid4()}",
            headers=auth_headers(user_admin),
        )
        assert resp.status_code == 404
