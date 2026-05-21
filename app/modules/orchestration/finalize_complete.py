"""
FinalizeCompleteUseCase — Unit of Work que garante atomicidade total:
  1. Finaliza a OS (status → FINALIZADA, finished_at = now)
  2. Reduz estoque atomicamente para cada item PECA da OS (FOR UPDATE)
  3. Cria entrada financeira de RECEITA para o valor total da OS
  4. Dispara task Celery de NF-e APÓS o commit (nunca antes)

Se qualquer etapa falhar → rollback total (nenhum efeito colateral).

Design: todos os passos usam a MESMA sessão SQLAlchemy (mesma transação).
flush() é chamado ao final para materializar no banco sem comitar.
O commit acontece apenas uma vez, ao sair do contexto de get_db_session().
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
from app.models.service_order import ItemType, ServiceOrder, ServiceOrderStatus
from app.modules.financial.service import FinancialService
from app.modules.stock.repository import StockItemRepository
from app.modules.stock.service import StockService
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.service_order_repository import ServiceOrderRepository

logger = get_logger(__name__)


def _build_idempotency_key(service_order_id: uuid.UUID) -> str:
    raw = f"nfe:{service_order_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


class FinalizeCompleteUseCase:
    """
    Orchestrates OS finalization with stock reduction and financial entry
    in a single database transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._so_repo = ServiceOrderRepository(session)
        self._invoice_repo = InvoiceRepository(session)
        self._stock_item_repo = StockItemRepository(session)

    async def finalize_with_stock_and_financial(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        notes: str | None = None,
        reduce_stock: bool = True,
    ) -> ServiceOrder:
        """
        Executes the full finalization flow atomically.

        Steps:
          1. Acquires FOR UPDATE lock on ServiceOrder
          2. Validates EM_ANDAMENTO → FINALIZADA transition
          3. Validates items exist
          4. Optionally reduces stock for each PECA item (graceful if no stock item found)
          5. Checks idempotency for Invoice
          6. Creates Invoice (PENDENTE) if not exists
          7. Creates FinancialEntry RECEITA (idempotent)
          8. Updates OS status + finished_at
          9. Flushes (not commits) — caller's session context commits

        Returns the finalized ServiceOrder.
        Caller is responsible for dispatching Celery task AFTER session commit.
        """

        # Step 1: Acquire FOR UPDATE lock on OS
        order = await self._so_repo.get_by_id_and_tenant_with_lock(order_id, tenant_id)
        if order is None:
            raise ResourceNotFoundException("Ordem de Serviço", str(order_id))

        # Step 2: Validate status transition
        current = ServiceOrderStatus(order.status)
        if not current.can_transition_to(ServiceOrderStatus.FINALIZADA):
            raise InvalidStatusTransitionException(
                "OS", current.value, ServiceOrderStatus.FINALIZADA.value
            )

        # Step 3: Validate items exist — reload with items
        full_order = await self._so_repo.get_by_id_and_tenant(order_id, tenant_id)
        if full_order is None or not full_order.items:
            raise BusinessRuleException("OS não pode ser finalizada sem itens")

        # Recalculate totals before finalization
        full_order.recalculate_totals()

        # Step 4: Reduce stock for PECA items
        if reduce_stock:
            peca_items = [
                i for i in full_order.items if i.item_type == ItemType.PECA
            ]
            for item in peca_items:
                if not item.part_number:
                    logger.warning(
                        "peca_sem_part_number",
                        item_id=str(item.id),
                        description=item.description,
                    )
                    continue

                # Look up StockItem by sku=part_number for this tenant
                stock_item = await self._stock_item_repo.get_by_sku_and_tenant(
                    item.part_number, tenant_id
                )
                if stock_item is None:
                    logger.warning(
                        "stock_item_not_found_for_peca",
                        part_number=item.part_number,
                        tenant_id=str(tenant_id),
                        os_item_id=str(item.id),
                    )
                    continue  # graceful skip — no stock item registered

                await StockService.reduce_for_os(
                    session=self._session,
                    tenant_id=tenant_id,
                    stock_item_id=stock_item.id,
                    quantity=item.quantity,
                    service_order_id=order_id,
                )

        # Step 5: Check Invoice idempotency
        idempotency_key = _build_idempotency_key(order_id)
        existing_invoice = await self._invoice_repo.get_by_service_order_id(order_id)

        if existing_invoice is not None:
            if existing_invoice.status in {
                InvoiceStatus.AUTORIZADA,
                InvoiceStatus.PROCESSANDO,
            }:
                raise InvoiceAlreadyExistsException(str(order_id))
            # REJEITADA ou ERRO: allow re-dispatch of Celery task
            invoice = existing_invoice
            logger.warning(
                "nfe_redespachada_complete",
                os_id=str(order_id),
                invoice_id=str(existing_invoice.id),
                status_anterior=existing_invoice.status,
            )
        else:
            # Step 6: Create Invoice (PENDENTE) in same transaction
            invoice = await self._invoice_repo.create(
                tenant_id=tenant_id,
                service_order_id=order_id,
                idempotency_key=idempotency_key,
                status=InvoiceStatus.PENDENTE,
                total_amount=full_order.total_amount,
            )

        # Step 7: Create FinancialEntry RECEITA (idempotent)
        await FinancialService.register_revenue_for_os(
            session=self._session,
            tenant_id=tenant_id,
            service_order_id=order_id,
            amount=full_order.total_amount,
            os_number=full_order.number,
        )

        # Step 8: Update OS status
        full_order.status = ServiceOrderStatus.FINALIZADA
        full_order.finished_at = datetime.now(timezone.utc)
        if notes:
            full_order.technician_notes = notes

        self._session.add(full_order)

        # Step 9: Flush — materializes all changes without committing
        # The session context manager in get_db_session() will commit
        await self._session.flush()

        logger.info(
            "os_finalized_complete",
            os_id=str(order_id),
            os_number=full_order.number,
            invoice_id=str(invoice.id),
            total_amount=str(full_order.total_amount),
            reduce_stock=reduce_stock,
        )

        return full_order
