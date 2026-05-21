"""
Tests for the Stock module.

Covers:
  - create stock item
  - list items (pagination)
  - add movement (ENTRADA increases qty, SAIDA decreases qty)
  - reduce_for_os atomicity
  - insufficient stock raises BusinessRuleException
  - multi-tenant isolation
  - soft delete
"""
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, DuplicateResourceException, ResourceNotFoundException
from app.models.tenant import Tenant
from app.modules.stock.models import MovementType, StockItem, StockMovement
from app.modules.stock.schemas import StockItemCreate, StockItemUpdate, StockMovementCreate
from app.modules.stock.service import StockService


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _create_item(session: AsyncSession, tenant_id: uuid.UUID, sku: str = "FILTRO-001", qty: Decimal = Decimal("10.000")) -> StockItem:
    svc = StockService(session)
    data = StockItemCreate(
        sku=sku,
        description="Filtro de óleo motor",
        ncm_code="84212300",
        unit="UN",
        quantity=qty,
        min_quantity=Decimal("2.000"),
        cost_price=Decimal("45.00"),
        sale_price=Decimal("75.00"),
    )
    return await svc.create_item(tenant_id, data)


# ── Tests: Create ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_stock_item(db_session: AsyncSession, tenant: Tenant):
    svc = StockService(db_session)
    data = StockItemCreate(
        sku="OLEO-15W40",
        description="Óleo 15W40 Mineral",
        unit="LT",
        quantity=Decimal("50.000"),
        min_quantity=Decimal("10.000"),
        cost_price=Decimal("12.50"),
        sale_price=Decimal("20.00"),
    )
    item = await svc.create_item(tenant.id, data)

    assert item.id is not None
    assert item.sku == "OLEO-15W40"
    assert item.quantity == Decimal("50.000")
    assert item.tenant_id == tenant.id
    assert item.active is True
    assert item.deleted_at is None


@pytest.mark.asyncio
async def test_create_stock_item_duplicate_sku_raises(db_session: AsyncSession, tenant: Tenant):
    await _create_item(db_session, tenant.id, sku="DUP-SKU")
    with pytest.raises(DuplicateResourceException):
        await _create_item(db_session, tenant.id, sku="DUP-SKU")


@pytest.mark.asyncio
async def test_create_stock_item_with_initial_movement(db_session: AsyncSession, tenant: Tenant):
    """Creating an item with qty > 0 should auto-create an ENTRADA movement."""
    item = await _create_item(db_session, tenant.id, qty=Decimal("5.000"))
    assert any(m.movement_type == MovementType.ENTRADA for m in item.movements)


# ── Tests: List ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_stock_items_pagination(db_session: AsyncSession, tenant: Tenant):
    svc = StockService(db_session)
    for i in range(5):
        data = StockItemCreate(
            sku=f"SKU-{i:03d}",
            description=f"Item {i}",
            quantity=Decimal("0.000"),
            min_quantity=Decimal("0.000"),
            cost_price=Decimal("0.00"),
            sale_price=Decimal("0.00"),
        )
        await svc.create_item(tenant.id, data)

    result = await svc.list_items(tenant.id, page=1, page_size=3)
    assert result.total == 5
    assert len(result.items) == 3
    assert result.pages == 2

    result_p2 = await svc.list_items(tenant.id, page=2, page_size=3)
    assert len(result_p2.items) == 2


# ── Tests: Movements ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_movement_entrada_increases_quantity(db_session: AsyncSession, tenant: Tenant):
    item = await _create_item(db_session, tenant.id, qty=Decimal("0.000"))
    svc = StockService(db_session)

    movement = await svc.add_movement(
        tenant.id,
        item.id,
        StockMovementCreate(
            movement_type=MovementType.ENTRADA,
            quantity=Decimal("20.000"),
            unit_cost=Decimal("45.00"),
            reason="Compra de estoque",
        ),
    )

    assert movement.movement_type == MovementType.ENTRADA
    assert movement.quantity_before == Decimal("0.000")
    assert movement.quantity_after == Decimal("20.000")

    updated_item = await svc.get_item(tenant.id, item.id)
    assert updated_item.quantity == Decimal("20.000")


@pytest.mark.asyncio
async def test_add_movement_saida_decreases_quantity(db_session: AsyncSession, tenant: Tenant):
    item = await _create_item(db_session, tenant.id, qty=Decimal("10.000"))
    svc = StockService(db_session)

    movement = await svc.add_movement(
        tenant.id,
        item.id,
        StockMovementCreate(
            movement_type=MovementType.SAIDA,
            quantity=Decimal("3.000"),
        ),
    )

    assert movement.quantity_before == Decimal("10.000")
    assert movement.quantity_after == Decimal("7.000")

    updated_item = await svc.get_item(tenant.id, item.id)
    assert updated_item.quantity == Decimal("7.000")


@pytest.mark.asyncio
async def test_insufficient_stock_raises_business_rule_exception(db_session: AsyncSession, tenant: Tenant):
    item = await _create_item(db_session, tenant.id, qty=Decimal("2.000"))
    svc = StockService(db_session)

    with pytest.raises(BusinessRuleException, match="Estoque insuficiente"):
        await svc.add_movement(
            tenant.id,
            item.id,
            StockMovementCreate(
                movement_type=MovementType.SAIDA,
                quantity=Decimal("5.000"),
            ),
        )


# ── Tests: reduce_for_os ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reduce_for_os_success(db_session: AsyncSession, tenant: Tenant):
    item = await _create_item(db_session, tenant.id, qty=Decimal("10.000"))
    # Use None to avoid FK constraint violation in unit tests
    # (In production, a real OS ID is passed from finalize_complete)
    movement = await StockService.reduce_for_os(
        session=db_session,
        tenant_id=tenant.id,
        stock_item_id=item.id,
        quantity=Decimal("3.000"),
        service_order_id=None,
    )

    assert movement is not None
    assert movement.movement_type == MovementType.BAIXA_OS
    assert movement.quantity == Decimal("3.000")
    assert movement.quantity_after == Decimal("7.000")
    assert movement.service_order_id is None


@pytest.mark.asyncio
async def test_reduce_for_os_insufficient_stock_raises(db_session: AsyncSession, tenant: Tenant):
    item = await _create_item(db_session, tenant.id, qty=Decimal("1.000"))

    with pytest.raises(BusinessRuleException, match="Estoque insuficiente"):
        await StockService.reduce_for_os(
            session=db_session,
            tenant_id=tenant.id,
            stock_item_id=item.id,
            quantity=Decimal("5.000"),
            service_order_id=None,
        )


@pytest.mark.asyncio
async def test_reduce_for_os_item_not_found_returns_none(db_session: AsyncSession, tenant: Tenant):
    fake_item_id = uuid.uuid4()

    result = await StockService.reduce_for_os(
        session=db_session,
        tenant_id=tenant.id,
        stock_item_id=fake_item_id,
        quantity=Decimal("1.000"),
        service_order_id=None,
    )

    assert result is None


# ── Tests: Multi-tenant isolation ─────────────────────────────────────────────

@pytest_asyncio.fixture
async def tenant_b(db_session: AsyncSession) -> Tenant:
    from app.models.tenant import Tenant as TenantModel
    t = TenantModel(
        id=uuid.uuid4(),
        name="Oficina B",
        document="98765432000101",
        email="oficina_b@teste.com",
        razao_social="OFICINA B LTDA",
        nome_fantasia="Oficina B",
        crt="1",
        municipio="Campinas",
        uf="SP",
        cep="13010100",
        codigo_municipio="3509502",
        logradouro="Av. Brasil",
        numero="500",
        bairro="Centro",
        active=True,
    )
    db_session.add(t)
    await db_session.flush()
    return t


@pytest.mark.asyncio
async def test_multi_tenant_isolation(db_session: AsyncSession, tenant: Tenant, tenant_b: Tenant):
    """Item from tenant A should not be visible to tenant B."""
    item_a = await _create_item(db_session, tenant.id, sku="ITEM-A")

    svc = StockService(db_session)

    # Tenant B cannot get tenant A's item
    with pytest.raises(ResourceNotFoundException):
        await svc.get_item(tenant_b.id, item_a.id)

    # Tenant B's list is empty
    result = await svc.list_items(tenant_b.id)
    assert result.total == 0


# ── Tests: Soft delete ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_soft_delete_item_not_in_list(db_session: AsyncSession, tenant: Tenant):
    svc = StockService(db_session)
    item = await _create_item(db_session, tenant.id, sku="SOFT-DEL")

    # Verify it's in list before deletion
    before = await svc.list_items(tenant.id)
    assert before.total == 1

    await svc.delete_item(tenant.id, item.id)

    # Should not appear in list after soft delete
    after = await svc.list_items(tenant.id)
    assert after.total == 0

    # get_item should raise after soft delete
    with pytest.raises(ResourceNotFoundException):
        await svc.get_item(tenant.id, item.id)


@pytest.mark.asyncio
async def test_soft_delete_sets_deleted_at(db_session: AsyncSession, tenant: Tenant):
    svc = StockService(db_session)
    item = await _create_item(db_session, tenant.id, sku="DEL-CHECK")
    await svc.delete_item(tenant.id, item.id)

    # Verify deleted_at was set by querying directly
    from sqlalchemy import select
    from app.modules.stock.models import StockItem as SI
    result = await db_session.execute(select(SI).where(SI.id == item.id))
    fetched = result.scalar_one_or_none()
    assert fetched is not None
    assert fetched.deleted_at is not None
    assert fetched.active is False
