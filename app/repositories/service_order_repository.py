import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.service_order import ServiceOrder, ServiceOrderItem, ServiceOrderStatus
from app.repositories.base_repository import BaseRepository


class ServiceOrderRepository(BaseRepository[ServiceOrder]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ServiceOrder, session)

    async def get_by_id_and_tenant(
        self, order_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> ServiceOrder | None:
        stmt = (
            select(ServiceOrder)
            .where(
                ServiceOrder.id == order_id,
                ServiceOrder.tenant_id == tenant_id,
            )
            .options(
                selectinload(ServiceOrder.items),
                selectinload(ServiceOrder.client),
                selectinload(ServiceOrder.machine),
                selectinload(ServiceOrder.invoice),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_and_tenant_with_lock(
        self, order_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> ServiceOrder | None:
        """FOR UPDATE — garante exclusão mútua na finalização."""
        stmt = (
            select(ServiceOrder)
            .where(
                ServiceOrder.id == order_id,
                ServiceOrder.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_next_number(self, tenant_id: uuid.UUID) -> int:
        """Número sequencial de OS por tenant, thread-safe via MAX+1."""
        stmt = select(func.coalesce(func.max(ServiceOrder.number), 0)).where(
            ServiceOrder.tenant_id == tenant_id
        )
        result = await self.session.execute(stmt)
        return (result.scalar_one() or 0) + 1

    async def list_by_tenant(
        self,
        tenant_id: uuid.UUID,
        status: ServiceOrderStatus | None = None,
        client_id: uuid.UUID | None = None,
        machine_id: uuid.UUID | None = None,
        technician_user_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ServiceOrder], int]:
        filters = [ServiceOrder.tenant_id == tenant_id]
        if status:
            filters.append(ServiceOrder.status == status)
        if client_id:
            filters.append(ServiceOrder.client_id == client_id)
        if machine_id:
            filters.append(ServiceOrder.machine_id == machine_id)
        if technician_user_id:
            # Isolamento TECNICO: vê apenas suas próprias OS
            filters.append(ServiceOrder.technician_user_id == technician_user_id)
        return await self.list_paginated(
            *filters,
            page=page,
            page_size=page_size,
            order_by=ServiceOrder.number.desc(),
        )

    async def get_item_by_id(
        self, item_id: uuid.UUID, service_order_id: uuid.UUID
    ) -> ServiceOrderItem | None:
        stmt = select(ServiceOrderItem).where(
            ServiceOrderItem.id == item_id,
            ServiceOrderItem.service_order_id == service_order_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_machine_with_items(
        self,
        machine_id: uuid.UUID,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ServiceOrder], int]:
        """Paginado + selectinload de itens — zero N+1, usa ix_os_machine_historico."""
        filters = [
            ServiceOrder.machine_id == machine_id,
            ServiceOrder.tenant_id == tenant_id,
        ]

        count_stmt = (
            select(func.count())
            .select_from(ServiceOrder)
            .where(*filters)
        )
        total = (await self.session.execute(count_stmt)).scalar_one()

        offset = (page - 1) * page_size
        stmt = (
            select(ServiceOrder)
            .options(
                selectinload(ServiceOrder.items),
                selectinload(ServiceOrder.client),
                selectinload(ServiceOrder.machine),
            )
            .where(*filters)
            .order_by(ServiceOrder.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def delete_items(self, service_order_id: uuid.UUID) -> None:
        items = await self.session.execute(
            select(ServiceOrderItem).where(
                ServiceOrderItem.service_order_id == service_order_id
            )
        )
        for item in items.scalars().all():
            await self.session.delete(item)
        await self.session.flush()
