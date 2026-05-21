import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleException,
    DuplicateResourceException,
    ResourceNotFoundException,
)
from app.core.logging import get_logger
from app.modules.stock.models import MovementType, StockItem, StockMovement
from app.modules.stock.repository import StockItemRepository, StockMovementRepository
from app.modules.stock.schemas import (
    StockItemCreate,
    StockItemListResponse,
    StockItemResponse,
    StockItemUpdate,
    StockMovementCreate,
    StockMovementResponse,
)

logger = get_logger(__name__)


class StockService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = StockItemRepository(session)
        self._movement_repo = StockMovementRepository(session)

    async def create_item(
        self, tenant_id: uuid.UUID, data: StockItemCreate
    ) -> StockItem:
        existing = await self._repo.get_by_sku_and_tenant(data.sku, tenant_id)
        if existing is not None:
            raise DuplicateResourceException("StockItem", "sku", data.sku)

        item = await self._repo.create(
            tenant_id=tenant_id,
            sku=data.sku,
            description=data.description,
            ncm_code=data.ncm_code,
            unit=data.unit,
            quantity=data.quantity,
            min_quantity=data.min_quantity,
            cost_price=data.cost_price,
            sale_price=data.sale_price,
            active=True,
        )

        # Create initial ENTRADA movement if quantity > 0
        if data.quantity > Decimal("0.000"):
            movement = StockMovement(
                tenant_id=tenant_id,
                stock_item_id=item.id,
                movement_type=MovementType.ENTRADA,
                quantity=data.quantity,
                quantity_before=Decimal("0.000"),
                quantity_after=data.quantity,
                unit_cost=data.cost_price,
                reason="Estoque inicial",
            )
            self._session.add(movement)
            await self._session.flush()
            # Refresh to reflect the new movement in the relationship
            await self._session.refresh(item, attribute_names=["movements"])

        logger.info("stock_item_created", sku=data.sku, tenant_id=str(tenant_id))
        return item

    async def get_item(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> StockItem:
        item = await self._repo.get_by_id_and_tenant(item_id, tenant_id)
        if item is None:
            raise ResourceNotFoundException("StockItem", str(item_id))
        return item

    async def list_items(
        self,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> StockItemListResponse:
        items, total = await self._repo.list_by_tenant(
            tenant_id, page=page, page_size=page_size
        )
        pages = max(1, -(-total // page_size))
        return StockItemListResponse(
            items=[StockItemResponse.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def update_item(
        self,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        data: StockItemUpdate,
    ) -> StockItem:
        item = await self._repo.get_by_id_and_tenant(item_id, tenant_id)
        if item is None:
            raise ResourceNotFoundException("StockItem", str(item_id))

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(item, field, value)

        updated = await self._repo.save(item)
        logger.info("stock_item_updated", item_id=str(item_id))
        return updated

    async def delete_item(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> None:
        item = await self._repo.get_by_id_and_tenant(item_id, tenant_id)
        if item is None:
            raise ResourceNotFoundException("StockItem", str(item_id))

        item.deleted_at = datetime.now(timezone.utc)
        item.active = False
        await self._repo.save(item)
        logger.info("stock_item_soft_deleted", item_id=str(item_id))

    async def add_movement(
        self,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        data: StockMovementCreate,
    ) -> StockMovement:
        # Use lock to prevent concurrent quantity corruption
        item = await self._repo.get_by_id_and_tenant_with_lock(item_id, tenant_id)
        if item is None:
            raise ResourceNotFoundException("StockItem", str(item_id))

        quantity_before = item.quantity

        if data.movement_type in {MovementType.ENTRADA, MovementType.AJUSTE}:
            if data.movement_type == MovementType.AJUSTE:
                # For AJUSTE, quantity represents the new absolute quantity
                quantity_after = data.quantity
                movement_qty = data.quantity - quantity_before
            else:
                quantity_after = quantity_before + data.quantity
                movement_qty = data.quantity
        elif data.movement_type in {MovementType.SAIDA, MovementType.BAIXA_OS, MovementType.RESERVA}:
            if quantity_before < data.quantity:
                raise BusinessRuleException(
                    f"Estoque insuficiente: disponível={quantity_before}, "
                    f"solicitado={data.quantity}"
                )
            quantity_after = quantity_before - data.quantity
            movement_qty = data.quantity
        else:
            quantity_after = quantity_before + data.quantity
            movement_qty = data.quantity

        item.quantity = quantity_after
        await self._repo.save(item)

        movement = StockMovement(
            tenant_id=tenant_id,
            stock_item_id=item_id,
            service_order_id=data.service_order_id,
            movement_type=data.movement_type,
            quantity=movement_qty,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            unit_cost=data.unit_cost,
            reason=data.reason,
            reference=data.reference,
        )
        self._session.add(movement)
        await self._session.flush()
        await self._session.refresh(movement)

        logger.info(
            "stock_movement_created",
            item_id=str(item_id),
            type=data.movement_type.value,
            qty=str(movement_qty),
            qty_after=str(quantity_after),
        )
        return movement

    async def list_movements(
        self,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StockMovement], int]:
        # Verify item exists and belongs to tenant
        item = await self._repo.get_by_id_and_tenant(item_id, tenant_id)
        if item is None:
            raise ResourceNotFoundException("StockItem", str(item_id))

        return await self._movement_repo.list_by_item(
            stock_item_id=item_id,
            tenant_id=tenant_id,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    async def reduce_for_os(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        stock_item_id: uuid.UUID,
        quantity: Decimal,
        service_order_id: uuid.UUID,
    ) -> StockMovement | None:
        """
        Atomic stock reduction for OS finalization.

        Uses FOR UPDATE lock to prevent concurrent over-reduction.
        Raises BusinessRuleException if insufficient stock.
        Returns the created movement, or None if item not found (graceful skip).
        """
        repo = StockItemRepository(session)
        movement_repo = StockMovementRepository(session)

        item = await repo.get_by_id_and_tenant_with_lock(stock_item_id, tenant_id)
        if item is None:
            logger.warning(
                "stock_item_not_found_for_os_reduction",
                stock_item_id=str(stock_item_id),
                tenant_id=str(tenant_id),
            )
            return None

        if item.quantity < quantity:
            raise BusinessRuleException(
                f"Estoque insuficiente para o item '{item.sku}': "
                f"disponível={item.quantity}, solicitado={quantity}"
            )

        quantity_before = item.quantity
        quantity_after = quantity_before - quantity

        item.quantity = quantity_after
        session.add(item)

        movement = StockMovement(
            tenant_id=tenant_id,
            stock_item_id=item.id,
            service_order_id=service_order_id,
            movement_type=MovementType.BAIXA_OS,
            quantity=quantity,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            unit_cost=item.cost_price,
            reason=f"Baixa automática por finalização da OS {service_order_id}",
            reference=str(service_order_id),
        )
        session.add(movement)
        await session.flush()

        logger.info(
            "stock_reduced_for_os",
            item_id=str(item.id),
            sku=item.sku,
            qty_reduced=str(quantity),
            qty_after=str(quantity_after),
            service_order_id=str(service_order_id),
        )
        return movement
