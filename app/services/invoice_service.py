"""
InvoiceService — consultas e reprocessamento de NF-e.
A lógica de geração/transmissão está em app.workers.nfe_processor (Passo 3).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BusinessRuleException, ResourceNotFoundException
from app.core.logging import get_logger
from app.models.invoice import Invoice, InvoiceStatus
from app.repositories.invoice_repository import InvoiceRepository
from app.schemas.common import PaginatedResponse

logger = get_logger(__name__)


class InvoiceService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = InvoiceRepository(session)

    async def get(self, tenant_id: uuid.UUID, invoice_id: uuid.UUID) -> Invoice:
        invoice = await self._repo.get_by_id(invoice_id)
        if invoice is None or invoice.tenant_id != tenant_id:
            raise ResourceNotFoundException("NF-e", str(invoice_id))
        return invoice

    async def get_by_service_order(
        self, tenant_id: uuid.UUID, service_order_id: uuid.UUID
    ) -> Invoice:
        invoice = await self._repo.get_by_service_order_id(service_order_id)
        if invoice is None or invoice.tenant_id != tenant_id:
            raise ResourceNotFoundException("NF-e para OS", str(service_order_id))
        return invoice

    async def list(
        self,
        tenant_id: uuid.UUID,
        status: InvoiceStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        items, total = await self._repo.list_by_tenant(
            tenant_id, status=status, page=page, page_size=page_size
        )
        return PaginatedResponse.build(items, total, page, page_size)

    async def retry(self, tenant_id: uuid.UUID, invoice_id: uuid.UUID) -> Invoice:
        """Reprocessa manualmente uma NF-e em estado ERRO ou REJEITADA."""
        invoice = await self.get(tenant_id, invoice_id)

        if invoice.status not in {InvoiceStatus.ERRO, InvoiceStatus.REJEITADA}:
            raise BusinessRuleException(
                f"NF-e só pode ser reprocessada nos estados ERRO ou REJEITADA. "
                f"Status atual: {invoice.status}"
            )

        if invoice.retry_count >= settings.CELERY_TASK_MAX_RETRIES:
            raise BusinessRuleException(
                f"Limite de {settings.CELERY_TASK_MAX_RETRIES} tentativas atingido"
            )

        from app.workers.tasks import process_invoice_task

        process_invoice_task.apply_async(
            kwargs={
                "invoice_id": str(invoice_id),
                "idempotency_key": invoice.idempotency_key,
            },
            queue="nfe",
        )

        logger.info(
            "nfe_retry_manual",
            invoice_id=str(invoice_id),
            retry_count=invoice.retry_count,
            tenant_id=str(tenant_id),
        )
        return invoice

    async def get_xml(self, tenant_id: uuid.UUID, invoice_id: uuid.UUID) -> str:
        invoice = await self.get(tenant_id, invoice_id)
        if invoice.status != InvoiceStatus.AUTORIZADA:
            raise BusinessRuleException("XML disponível apenas para NF-e autorizada")
        if not invoice.xml_content:
            raise BusinessRuleException("XML não encontrado para esta NF-e")
        return invoice.xml_content

    async def get_danfe_path(self, tenant_id: uuid.UUID, invoice_id: uuid.UUID) -> str:
        invoice = await self.get(tenant_id, invoice_id)
        if invoice.status != InvoiceStatus.AUTORIZADA:
            raise BusinessRuleException("DANFE disponível apenas para NF-e autorizada")
        if not invoice.danfe_path:
            raise BusinessRuleException("DANFE não encontrado para esta NF-e")
        return invoice.danfe_path
