"""
Tests for the orchestration module (FinalizeCompleteUseCase).

Covers:
  - Happy path: OS status → FINALIZADA, stock reduced, revenue created
  - Rollback: insufficient stock → nothing committed
  - Idempotency: calling finalize twice → 2nd call raises InvoiceAlreadyExistsException
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleException,
    InvoiceAlreadyExistsException,
    InvalidStatusTransitionException,
)
from app.models.service_order import (
    ItemType,
    ServiceOrder,
    ServiceOrderItem,
    ServiceOrderStatus,
)
from app.models.tenant import Tenant
from app.models.client import Client
from app.models.invoice import InvoiceStatus
from app.modules.financial.repository import FinancialEntryRepository
from app.modules.orchestration.finalize_complete import FinalizeCompleteUseCase
from app.modules.stock.models import StockItem
from app.modules.stock.schemas import StockItemCreate
from app.modules.stock.service import StockService
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.service_order_repository import ServiceOrderRepository


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def em_andamento_order_with_peca(
    db_session: AsyncSession,
    tenant: Tenant,
    client_entity: Client,
) -> ServiceOrder:
    """Service order in EM_ANDAMENTO with one SERVICO and one PECA item."""
    order = ServiceOrder(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        client_id=client_entity.id,
        number=100,
        status=ServiceOrderStatus.EM_ANDAMENTO,
        description="Manutenção preventiva",
        opened_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        total_services=Decimal("350.00"),
        total_parts=Decimal("90.00"),
        total_discount=Decimal("0.00"),
        total_amount=Decimal("440.00"),
    )
    db_session.add(order)
    await db_session.flush()

    items = [
        ServiceOrderItem(
            id=uuid.uuid4(),
            service_order_id=order.id,
            item_type=ItemType.SERVICO,
            description="Troca de óleo",
            quantity=Decimal("1.000"),
            unit_price=Decimal("350.00"),
            discount=Decimal("0.00"),
            total_price=Decimal("350.00"),
        ),
        ServiceOrderItem(
            id=uuid.uuid4(),
            service_order_id=order.id,
            item_type=ItemType.PECA,
            description="Filtro de óleo",
            ncm_code="84212300",
            part_number="FO-4521",
            quantity=Decimal("2.000"),
            unit_price=Decimal("45.00"),
            discount=Decimal("0.00"),
            total_price=Decimal("90.00"),
        ),
    ]
    db_session.add_all(items)
    await db_session.flush()
    await db_session.refresh(order, attribute_names=["items"])
    return order


@pytest_asyncio.fixture
async def stock_item_for_peca(
    db_session: AsyncSession,
    tenant: Tenant,
) -> StockItem:
    """Stock item with sku=FO-4521 matching the OS PECA part_number."""
    svc = StockService(db_session)
    data = StockItemCreate(
        sku="FO-4521",
        description="Filtro de óleo motor",
        ncm_code="84212300",
        unit="UN",
        quantity=Decimal("10.000"),
        min_quantity=Decimal("2.000"),
        cost_price=Decimal("45.00"),
        sale_price=Decimal("75.00"),
    )
    return await svc.create_item(tenant.id, data)


# ── Tests: Happy path ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_finalize_complete_happy_path(
    db_session: AsyncSession,
    tenant: Tenant,
    em_andamento_order_with_peca: ServiceOrder,
    stock_item_for_peca: StockItem,
):
    use_case = FinalizeCompleteUseCase(db_session)
    order = await use_case.finalize_with_stock_and_financial(
        tenant_id=tenant.id,
        order_id=em_andamento_order_with_peca.id,
        notes="Serviço concluído com sucesso",
        reduce_stock=True,
    )

    # OS status should be FINALIZADA
    assert order.status == ServiceOrderStatus.FINALIZADA
    assert order.finished_at is not None

    # Invoice should exist
    invoice_repo = InvoiceRepository(db_session)
    invoice = await invoice_repo.get_by_service_order_id(order.id)
    assert invoice is not None
    assert invoice.status == InvoiceStatus.PENDENTE

    # Stock should be reduced
    stock_svc = StockService(db_session)
    updated_stock = await stock_svc.get_item(tenant.id, stock_item_for_peca.id)
    assert updated_stock.quantity == Decimal("8.000")  # 10 - 2 = 8

    # Financial entry should exist
    fin_repo = FinancialEntryRepository(db_session)
    idempotency_key = f"receita:os:{em_andamento_order_with_peca.id}"
    fin_entry = await fin_repo.get_by_idempotency_key(idempotency_key)
    assert fin_entry is not None
    assert fin_entry.amount == order.total_amount


@pytest.mark.asyncio
async def test_finalize_complete_no_stock_reduce(
    db_session: AsyncSession,
    tenant: Tenant,
    em_andamento_order_with_peca: ServiceOrder,
    stock_item_for_peca: StockItem,
):
    """With reduce_stock=False, stock should remain unchanged."""
    use_case = FinalizeCompleteUseCase(db_session)
    order = await use_case.finalize_with_stock_and_financial(
        tenant_id=tenant.id,
        order_id=em_andamento_order_with_peca.id,
        reduce_stock=False,
    )

    assert order.status == ServiceOrderStatus.FINALIZADA

    # Stock should be untouched
    stock_svc = StockService(db_session)
    updated_stock = await stock_svc.get_item(tenant.id, stock_item_for_peca.id)
    assert updated_stock.quantity == Decimal("10.000")  # unchanged


# ── Tests: Rollback on insufficient stock ────────────────────────────────────

@pytest.mark.asyncio
async def test_finalize_complete_rollback_on_insufficient_stock(
    db_session: AsyncSession,
    tenant: Tenant,
    client_entity: Client,
):
    """If stock is insufficient, BusinessRuleException is raised and nothing is committed."""
    # Create stock item with insufficient quantity
    svc = StockService(db_session)
    stock = await svc.create_item(
        tenant.id,
        StockItemCreate(
            sku="FO-LOW",
            description="Filtro baixo estoque",
            quantity=Decimal("1.000"),  # only 1 available
            min_quantity=Decimal("0.000"),
            cost_price=Decimal("10.00"),
            sale_price=Decimal("20.00"),
        ),
    )

    # Create order with PECA that needs 5 units
    order = ServiceOrder(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        client_id=client_entity.id,
        number=200,
        status=ServiceOrderStatus.EM_ANDAMENTO,
        description="Serviço com estoque insuficiente",
        opened_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        total_services=Decimal("0.00"),
        total_parts=Decimal("100.00"),
        total_discount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
    )
    db_session.add(order)
    await db_session.flush()

    item = ServiceOrderItem(
        id=uuid.uuid4(),
        service_order_id=order.id,
        item_type=ItemType.PECA,
        description="Peça sem estoque suficiente",
        part_number="FO-LOW",
        quantity=Decimal("5.000"),  # need 5, have 1
        unit_price=Decimal("20.00"),
        discount=Decimal("0.00"),
        total_price=Decimal("100.00"),
    )
    db_session.add(item)
    await db_session.flush()

    use_case = FinalizeCompleteUseCase(db_session)

    with pytest.raises(BusinessRuleException, match="Estoque insuficiente"):
        await use_case.finalize_with_stock_and_financial(
            tenant_id=tenant.id,
            order_id=order.id,
            reduce_stock=True,
        )

    # Stock should be unchanged
    stock_after = await svc.get_item(tenant.id, stock.id)
    assert stock_after.quantity == Decimal("1.000")


# ── Tests: Idempotency ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_finalize_complete_idempotency_second_call_raises(
    db_session: AsyncSession,
    tenant: Tenant,
    em_andamento_order_with_peca: ServiceOrder,
    stock_item_for_peca: StockItem,
):
    """Calling finalize twice on the same OS raises InvoiceAlreadyExistsException."""
    use_case = FinalizeCompleteUseCase(db_session)

    # First call succeeds
    await use_case.finalize_with_stock_and_financial(
        tenant_id=tenant.id,
        order_id=em_andamento_order_with_peca.id,
        reduce_stock=False,
    )

    # Second call fails because OS is now FINALIZADA (invalid status transition)
    with pytest.raises(InvalidStatusTransitionException):
        await use_case.finalize_with_stock_and_financial(
            tenant_id=tenant.id,
            order_id=em_andamento_order_with_peca.id,
            reduce_stock=False,
        )


@pytest.mark.asyncio
async def test_finalize_complete_not_found_raises(
    db_session: AsyncSession,
    tenant: Tenant,
):
    use_case = FinalizeCompleteUseCase(db_session)
    from app.core.exceptions import ResourceNotFoundException

    with pytest.raises(ResourceNotFoundException):
        await use_case.finalize_with_stock_and_financial(
            tenant_id=tenant.id,
            order_id=uuid.uuid4(),
        )
