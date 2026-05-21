"""
Testes de integração do ServiceOrderService.
Inclui: criação, atualização, transições de status e disparo da NF-e.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    BusinessRuleException,
    InvalidStatusTransitionException,
    ResourceNotFoundException,
)
from app.models.invoice import InvoiceStatus
from app.models.service_order import ItemType, ServiceOrderStatus
from app.schemas.service_order import (
    ServiceOrderCreate,
    ServiceOrderItemCreate,
    ServiceOrderUpdate,
)
from app.services.service_order_service import ServiceOrderService

pytestmark = pytest.mark.integration


class TestServiceOrderCreation:
    async def test_cria_os_basica(self, db_session, tenant, client_entity):
        data = ServiceOrderCreate(
            client_id=client_entity.id,
            description="Manutenção preventiva",
        )
        order = await ServiceOrderService(db_session).create(tenant.id, data)
        assert order.id is not None
        assert order.status == ServiceOrderStatus.ABERTA
        assert order.tenant_id == tenant.id
        assert order.client_id == client_entity.id
        assert order.number >= 1

    async def test_cria_os_com_maquina(self, db_session, tenant, client_entity, machine):
        data = ServiceOrderCreate(
            client_id=client_entity.id,
            machine_id=machine.id,
        )
        order = await ServiceOrderService(db_session).create(tenant.id, data)
        assert order.machine_id == machine.id

    async def test_cria_os_com_itens(self, db_session, tenant, client_entity):
        data = ServiceOrderCreate(
            client_id=client_entity.id,
            items=[
                ServiceOrderItemCreate(
                    item_type=ItemType.SERVICO,
                    description="Troca de óleo",
                    quantity=Decimal("1"),
                    unit_price=Decimal("150.00"),
                ),
                ServiceOrderItemCreate(
                    item_type=ItemType.PECA,
                    description="Óleo 10W40",
                    quantity=Decimal("5"),
                    unit_price=Decimal("22.00"),
                ),
            ],
        )
        order = await ServiceOrderService(db_session).create(tenant.id, data)
        assert len(order.items) == 2

    async def test_numero_sequencial_por_tenant(
        self, db_session, tenant, client_entity
    ):
        svc = ServiceOrderService(db_session)
        o1 = await svc.create(tenant.id, ServiceOrderCreate(client_id=client_entity.id))
        o2 = await svc.create(tenant.id, ServiceOrderCreate(client_id=client_entity.id))
        assert o2.number == o1.number + 1

    async def test_rejeita_cliente_inativo(self, db_session, tenant, client_entity):
        client_entity.active = False
        db_session.add(client_entity)
        await db_session.flush()
        with pytest.raises(BusinessRuleException):
            await ServiceOrderService(db_session).create(
                tenant.id, ServiceOrderCreate(client_id=client_entity.id)
            )

    async def test_rejeita_maquina_de_outro_cliente(
        self, db_session, tenant, client_entity, machine
    ):
        outro_client_id = uuid.uuid4()
        from app.models.client import Client, DocumentType
        outro = Client(
            id=outro_client_id,
            tenant_id=tenant.id,
            name="Outro",
            document="11122233344",
            document_type=DocumentType.CPF,
            active=True,
        )
        db_session.add(outro)
        await db_session.flush()

        with pytest.raises(BusinessRuleException):
            await ServiceOrderService(db_session).create(
                tenant.id,
                ServiceOrderCreate(client_id=outro_client_id, machine_id=machine.id),
            )


class TestServiceOrderStatusTransition:
    async def test_transicao_aberta_para_em_andamento(
        self, db_session, tenant, open_service_order
    ):
        order = await ServiceOrderService(db_session).update_status(
            tenant.id, open_service_order.id, ServiceOrderStatus.EM_ANDAMENTO
        )
        assert order.status == ServiceOrderStatus.EM_ANDAMENTO
        assert order.started_at is not None

    async def test_transicao_invalida_aberta_para_finalizada(
        self, db_session, tenant, open_service_order
    ):
        with pytest.raises(InvalidStatusTransitionException):
            await ServiceOrderService(db_session).update_status(
                tenant.id, open_service_order.id, ServiceOrderStatus.FINALIZADA
            )

    async def test_nao_pode_editar_os_finalizada(
        self, db_session, tenant, service_order_with_items
    ):
        svc = ServiceOrderService(db_session)
        await svc.update_status(
            tenant.id, service_order_with_items.id, ServiceOrderStatus.EM_ANDAMENTO
        )
        with patch("app.workers.tasks.process_invoice_task") as mock_task:
            mock_task.apply_async = MagicMock()
            await svc.finalize(tenant.id, service_order_with_items.id)

        with pytest.raises(BusinessRuleException):
            await svc.update(
                tenant.id,
                service_order_with_items.id,
                ServiceOrderUpdate(description="Tentativa proibida"),
            )


class TestServiceOrderFinalization:
    async def test_finalizacao_dispara_celery_task(
        self, db_session, tenant, service_order_with_items
    ):
        svc = ServiceOrderService(db_session)
        await svc.update_status(
            tenant.id, service_order_with_items.id, ServiceOrderStatus.EM_ANDAMENTO
        )

        with patch("app.workers.tasks.process_invoice_task") as mock_task:
            mock_task.apply_async = MagicMock()
            order = await svc.finalize(tenant.id, service_order_with_items.id)

        assert order.status == ServiceOrderStatus.FINALIZADA
        assert order.finished_at is not None
        mock_task.apply_async.assert_called_once()

    async def test_finalizacao_cria_invoice_pendente(
        self, db_session, tenant, service_order_with_items
    ):
        svc = ServiceOrderService(db_session)
        await svc.update_status(
            tenant.id, service_order_with_items.id, ServiceOrderStatus.EM_ANDAMENTO
        )

        with patch("app.workers.tasks.process_invoice_task") as mock_task:
            mock_task.apply_async = MagicMock()
            await svc.finalize(tenant.id, service_order_with_items.id)

        from app.repositories.invoice_repository import InvoiceRepository
        repo = InvoiceRepository(db_session)
        invoice = await repo.get_by_service_order_id(service_order_with_items.id)

        assert invoice is not None
        assert invoice.status == InvoiceStatus.PENDENTE
        assert invoice.tenant_id == tenant.id

    async def test_idempotency_key_deterministica(
        self, db_session, tenant, service_order_with_items
    ):
        import hashlib
        expected_key = hashlib.sha256(
            f"nfe:{service_order_with_items.id}".encode()
        ).hexdigest()

        svc = ServiceOrderService(db_session)
        await svc.update_status(
            tenant.id, service_order_with_items.id, ServiceOrderStatus.EM_ANDAMENTO
        )

        with patch("app.workers.tasks.process_invoice_task") as mock_task:
            mock_task.apply_async = MagicMock()
            await svc.finalize(tenant.id, service_order_with_items.id)

        from app.repositories.invoice_repository import InvoiceRepository
        invoice = await InvoiceRepository(db_session).get_by_service_order_id(
            service_order_with_items.id
        )
        assert invoice.idempotency_key == expected_key

    async def test_finalizacao_sem_itens_falha(
        self, db_session, tenant, open_service_order
    ):
        svc = ServiceOrderService(db_session)
        await svc.update_status(
            tenant.id, open_service_order.id, ServiceOrderStatus.EM_ANDAMENTO
        )
        with pytest.raises(BusinessRuleException, match="sem itens"):
            await svc.finalize(tenant.id, open_service_order.id)

    async def test_task_celery_usa_fila_nfe(
        self, db_session, tenant, service_order_with_items
    ):
        svc = ServiceOrderService(db_session)
        await svc.update_status(
            tenant.id, service_order_with_items.id, ServiceOrderStatus.EM_ANDAMENTO
        )

        with patch("app.workers.tasks.process_invoice_task") as mock_task:
            mock_task.apply_async = MagicMock()
            await svc.finalize(tenant.id, service_order_with_items.id)

        call_kwargs = mock_task.apply_async.call_args
        assert call_kwargs.kwargs.get("queue") == "nfe" or (
            call_kwargs.args and "nfe" in str(call_kwargs)
        )
