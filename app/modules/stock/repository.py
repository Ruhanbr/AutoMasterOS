import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.stock.models import StockItem, StockMovement, MovementType
from app.repositories.base_repository import BaseRepository


class StockItemRepository(BaseRepository[StockItem]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(StockItem, session)

    async def get_by_id_and_tenant(
        self, item_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> StockItem | None:
        stmt = (
            select(StockItem)
            .where(
                StockItem.id == item_id,
                StockItem.tenant_id == tenant_id,
                StockItem.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_and_tenant_with_lock(
        self, item_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> StockItem | None:
        """SELECT ... FOR UPDATE — previne race condition na redução de estoque."""
        stmt = (
            select(StockItem)
            .where(
                StockItem.id == item_id,
                StockItem.tenant_id == tenant_id,
                StockItem.deleted_at.is_(None),
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_sku_and_tenant(
        self, sku: str, tenant_id: uuid.UUID
    ) -> StockItem | None:
        stmt = select(StockItem).where(
            StockItem.sku == sku,
            StockItem.tenant_id == tenant_id,
            StockItem.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_sku_and_tenant_with_lock(
        self, sku: str, tenant_id: uuid.UUID
    ) -> StockItem | None:
        """SELECT ... FOR UPDATE by SKU — used in reduce_for_os lookup."""
        stmt = (
            select(StockItem)
            .where(
                StockItem.sku == sku,
                StockItem.tenant_id == tenant_id,
                StockItem.deleted_at.is_(None),
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StockItem], int]:
        return await self.list_paginated(
            StockItem.tenant_id == tenant_id,
            StockItem.deleted_at.is_(None),
            page=page,
            page_size=page_size,
            order_by=StockItem.sku.asc(),
        )


class StockMovementRepository(BaseRepository[StockMovement]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(StockMovement, session)

    async def list_by_item(
        self,
        stock_item_id: uuid.UUID,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StockMovement], int]:
        return await self.list_paginated(
            StockMovement.stock_item_id == stock_item_id,
            StockMovement.tenant_id == tenant_id,
            page=page,
            page_size=page_size,
            order_by=StockMovement.created_at.desc(),
        )
