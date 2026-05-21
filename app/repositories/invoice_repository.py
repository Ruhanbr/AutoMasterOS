import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice, InvoiceStatus
from app.repositories.base_repository import BaseRepository


class InvoiceRepository(BaseRepository[Invoice]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Invoice, session)

    async def get_by_idempotency_key(self, key: str) -> Invoice | None:
        """
        Lookup principal para idempotência.
        O worker sempre checa esta chave antes de processar.
        """
        stmt = select(Invoice).where(Invoice.idempotency_key == key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key_with_lock(self, key: str) -> Invoice | None:
        """FOR UPDATE — evita processamento duplo em workers concorrentes."""
        stmt = (
            select(Invoice)
            .where(Invoice.idempotency_key == key)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_service_order_id(
        self, service_order_id: uuid.UUID
    ) -> Invoice | None:
        stmt = select(Invoice).where(Invoice.service_order_id == service_order_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_access_key(self, access_key: str) -> Invoice | None:
        stmt = select(Invoice).where(Invoice.access_key == access_key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: uuid.UUID,
        status: InvoiceStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Invoice], int]:
        filters = [Invoice.tenant_id == tenant_id]
        if status:
            filters.append(Invoice.status == status)
        return await self.list_paginated(*filters, page=page, page_size=page_size)

    async def list_retriable(self, max_retries: int) -> list[Invoice]:
        """Retorna NFs em ERRO ou REJEITADA elegíveis para nova tentativa."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        stmt = select(Invoice).where(
            Invoice.status.in_([InvoiceStatus.ERRO, InvoiceStatus.REJEITADA]),
            Invoice.retry_count < max_retries,
            Invoice.next_retry_at <= now,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
