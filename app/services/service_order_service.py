"""
ServiceOrderService — contém toda a lógica de negócio das OS.

O método `finalize()` é o ponto crítico:
  1. Adquire lock FOR UPDATE na OS (previne race condition)
  2. Valida transição de status
  3. Cria o registro Invoice com idempotency_key ANTES de despachar a task
  4. Faz commit da transação
  5. Só ENTÃO despacha a task Celery

Essa ordem garante que, se o worker falhar ou reiniciar, o registro
de Invoice já existe e o mecanismo de retry/idempotência entra em ação.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleException,
    InvoiceAlreadyExistsException,
    InvalidStatusTransitionException,
    ResourceNotFoundException,
)
from app.core.logging import get_logger
from app.models.invoice import Invoice, InvoiceStatus
from app.models.service_order import (
    ItemType,
    ServiceOrder,
    ServiceOrderItem,
    ServiceOrderStatus,
)
from app.repositories.client_repository import ClientRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.machine_repository import MachineRepository
from app.repositories.service_order_repository import ServiceOrderRepository
from app.schemas.common import PaginatedResponse
from app.schemas.service_order import (
    ServiceOrderCreate,
    ServiceOrderItemCreate,
    ServiceOrderUpdate,
)

logger = get_logger(__name__)


def _build_idempotency_key(service_order_id: uuid.UUID) -> str:
    """
    Chave determinística derivada do ID da OS.
    Idêntica em qualquer retry — nunca gera NF duplicada.
    """
    raw = f"nfe:{service_order_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


class ServiceOrderService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ServiceOrderRepository(session)
        self._invoice_repo = InvoiceRepository(session)
        self._client_repo = ClientRepository(session)
        self._machine_repo = MachineRepository(session)
        self._session = session

    # ─── Criação ──────────────────────────────────────────────────────────────

    async def create(
        self,
        tenant_id: uuid.UUID,
        data: ServiceOrderCreate,
        created_by_user_id: uuid.UUID | None = None,
    ) -> ServiceOrder:
        client = await self._client_repo.get_by_id_and_tenant(data.client_id, tenant_id)
        if client is None:
            raise ResourceNotFoundException("Cliente", str(data.client_id))
        if not client.active:
            raise BusinessRuleException("Cliente inativo não pode ter OS aberta")

        if data.machine_id:
            machine = await self._machine_repo.get_by_id_and_tenant(data.machine_id, tenant_id)
            if machine is None:
                raise ResourceNotFoundException("Máquina", str(data.machine_id))
            if machine.client_id != data.client_id:
                raise BusinessRuleException("Máquina não pertence ao cliente informado")

        number = await self._repo.get_next_number(tenant_id)

        order = await self._repo.create(
            tenant_id=tenant_id,
            client_id=data.client_id,
            machine_id=data.machine_id,
            number=number,
            status=ServiceOrderStatus.ABERTA,
            description=data.description,
            technician_name=data.technician_name,
            expected_delivery_at=data.expected_delivery_at,
            opened_at=datetime.now(timezone.utc),
            # Auto-assinatura: TECNICO fica vinculado à OS que ele mesmo abre
            technician_user_id=created_by_user_id,
        )

        if data.items:
            await self._upsert_items(order, data.items)

        logger.info(
            "os_criada",
            os_id=str(order.id),
            os_number=number,
            tenant_id=str(tenant_id),
            client_id=str(data.client_id),
        )
        return order

    # ─── Leitura ──────────────────────────────────────────────────────────────

    async def get(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> ServiceOrder:
        order = await self._repo.get_by_id_and_tenant(order_id, tenant_id)
        if order is None:
            raise ResourceNotFoundException("Ordem de Serviço", str(order_id))
        return order

    async def list(
        self,
        tenant_id: uuid.UUID,
        status: ServiceOrderStatus | None = None,
        client_id: uuid.UUID | None = None,
        machine_id: uuid.UUID | None = None,
        technician_user_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        items, total = await self._repo.list_by_tenant(
            tenant_id,
            status=status,
            client_id=client_id,
            machine_id=machine_id,
            technician_user_id=technician_user_id,
            page=page,
            page_size=page_size,
        )
        return PaginatedResponse.build(items, total, page, page_size)

    # ─── Atualização ──────────────────────────────────────────────────────────

    async def update(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, data: ServiceOrderUpdate
    ) -> ServiceOrder:
        order = await self.get(tenant_id, order_id)

        if order.status == ServiceOrderStatus.FINALIZADA:
            raise BusinessRuleException("OS finalizada não pode ser editada")

        update_data = data.model_dump(exclude_unset=True, exclude={"items"})
        for field, value in update_data.items():
            setattr(order, field, value)

        if data.items is not None:
            await self._repo.delete_items(order_id)
            order.items = []
            await self._upsert_items(order, data.items)

        order.recalculate_totals()
        updated = await self._repo.save(order)
        logger.info("os_atualizada", os_id=str(order_id))
        return updated

    # ─── Transição de Status ──────────────────────────────────────────────────

    async def update_status(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        target_status: ServiceOrderStatus,
        notes: str | None = None,
    ) -> ServiceOrder:
        target_status = ServiceOrderStatus(target_status)
        order = await self._repo.get_by_id_and_tenant_with_lock(order_id, tenant_id)
        if order is None:
            raise ResourceNotFoundException("Ordem de Serviço", str(order_id))

        current = ServiceOrderStatus(order.status)
        if not current.can_transition_to(target_status):
            raise InvalidStatusTransitionException("OS", current.value, target_status.value)

        order.status = target_status

        if target_status == ServiceOrderStatus.EM_ANDAMENTO:
            order.started_at = datetime.now(timezone.utc)
        elif target_status == ServiceOrderStatus.FINALIZADA:
            order.finished_at = datetime.now(timezone.utc)

        if notes:
            order.technician_notes = notes

        updated = await self._repo.save(order)
        logger.info(
            "os_status_atualizado",
            os_id=str(order_id),
            de=current.value,
            para=target_status.value,
        )
        return updated

    # ─── Finalização com disparo de NF-e ──────────────────────────────────────

    async def finalize(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, notes: str | None = None
    ) -> ServiceOrder:
        """
        Finaliza a OS e dispara automaticamente a emissão da NF-e.

        Fluxo garantido:
          OS EM_ANDAMENTO → FINALIZADA
          Invoice criada (PENDENTE) dentro da mesma transação
          Task Celery despachada APÓS o commit (nunca antes)
        """
        order = await self._repo.get_by_id_and_tenant_with_lock(order_id, tenant_id)
        if order is None:
            raise ResourceNotFoundException("Ordem de Serviço", str(order_id))

        current = ServiceOrderStatus(order.status)
        if not current.can_transition_to(ServiceOrderStatus.FINALIZADA):
            raise InvalidStatusTransitionException(
                "OS", current.value, ServiceOrderStatus.FINALIZADA.value
            )

        if not order.items:
            raise BusinessRuleException("OS não pode ser finalizada sem itens")

        # Idempotência: verifica se NF já foi criada para esta OS
        idempotency_key = _build_idempotency_key(order_id)
        existing_invoice = await self._invoice_repo.get_by_service_order_id(order_id)
        if existing_invoice is not None:
            if existing_invoice.status in {
                InvoiceStatus.AUTORIZADA,
                InvoiceStatus.PROCESSANDO,
            }:
                raise InvoiceAlreadyExistsException(str(order_id))
            # REJEITADA ou ERRO: permite re-despacho da task abaixo
            logger.warning(
                "nfe_redespachada",
                os_id=str(order_id),
                invoice_id=str(existing_invoice.id),
                status_anterior=existing_invoice.status,
            )
        else:
            # Cria o registro de NF-e dentro da mesma transação da OS
            order.recalculate_totals()
            existing_invoice = await self._invoice_repo.create(
                tenant_id=tenant_id,
                service_order_id=order_id,
                idempotency_key=idempotency_key,
                status=InvoiceStatus.PENDENTE,
                total_amount=order.total_amount,
            )

        # Transição de status da OS
        order.status = ServiceOrderStatus.FINALIZADA
        order.finished_at = datetime.now(timezone.utc)
        if notes:
            order.technician_notes = notes

        await self._repo.save(order)

        # Flush para garantir que ambos os registros estão no banco
        # antes de despachar a task (commit acontece ao sair do contexto da session)
        await self._session.flush()

        logger.info(
            "os_finalizada_nfe_pendente",
            os_id=str(order_id),
            invoice_id=str(existing_invoice.id),
            idempotency_key=idempotency_key,
            total_amount=str(order.total_amount),
        )

        # Importação local para evitar importação circular com o worker
        from app.workers.tasks import process_invoice_task

        process_invoice_task.apply_async(
            kwargs={
                "invoice_id": str(existing_invoice.id),
                "idempotency_key": idempotency_key,
            },
            queue="nfe",
            # Aguarda 2s para garantir que o commit da session foi finalizado
            countdown=2,
        )

        logger.info(
            "nfe_task_despachada",
            os_id=str(order_id),
            invoice_id=str(existing_invoice.id),
        )
        return order

    # ─── Itens ────────────────────────────────────────────────────────────────

    async def add_item(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        data: ServiceOrderItemCreate,
    ) -> ServiceOrder:
        order = await self.get(tenant_id, order_id)
        if order.status == ServiceOrderStatus.FINALIZADA:
            raise BusinessRuleException("Não é possível adicionar itens a uma OS finalizada")

        await self._upsert_items(order, [data])
        order.recalculate_totals()
        return await self._repo.save(order)

    async def remove_item(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        item_id: uuid.UUID,
    ) -> ServiceOrder:
        order = await self.get(tenant_id, order_id)
        if order.status == ServiceOrderStatus.FINALIZADA:
            raise BusinessRuleException("Não é possível remover itens de uma OS finalizada")

        item = await self._repo.get_item_by_id(item_id, order_id)
        if item is None:
            raise ResourceNotFoundException("Item", str(item_id))

        await self._repo.delete(item)
        order.items = [i for i in order.items if i.id != item_id]
        order.recalculate_totals()
        return await self._repo.save(order)

    # ─── Helpers privados ─────────────────────────────────────────────────────

    async def _upsert_items(
        self, order: ServiceOrder, items_data: list[ServiceOrderItemCreate]
    ) -> None:
        for item_data in items_data:
            item = ServiceOrderItem(
                service_order_id=order.id,
                item_type=item_data.item_type,
                description=item_data.description,
                ncm_code=item_data.ncm_code,
                part_number=item_data.part_number,
                quantity=item_data.quantity,
                unit_price=item_data.unit_price,
                discount=item_data.discount,
                total_price=(item_data.quantity * item_data.unit_price) - item_data.discount,
            )
            self._session.add(item)
        await self._session.flush()
        # Itens foram inseridos via FK sem atualizar order.items em memória;
        # refresh garante que o atributo reflita o estado real do banco.
        await self._session.refresh(order, attribute_names=["items"])
