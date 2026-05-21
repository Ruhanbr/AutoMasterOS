"""
Tests for the Financial module.

Covers:
  - register expense
  - revenue idempotency (calling register_revenue_for_os twice → only 1 entry)
  - get_summary (totals correct)
  - multi-tenant isolation
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.modules.financial.models import EntryType, FinancialEntry
from app.modules.financial.repository import FinancialEntryRepository
from app.modules.financial.schemas import FinancialExpenseCreate
from app.modules.financial.service import FinancialService


# ── Tests: Register expense ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_expense(db_session: AsyncSession, tenant: Tenant):
    svc = FinancialService(db_session)
    data = FinancialExpenseCreate(
        amount=Decimal("250.00"),
        description="Compra de ferramentas",
        category="Equipamentos",
        reference_date=datetime.now(timezone.utc),
    )
    entry = await svc.register_expense(tenant.id, data)

    assert entry.id is not None
    assert entry.entry_type == EntryType.DESPESA
    assert entry.amount == Decimal("250.00")
    assert entry.description == "Compra de ferramentas"
    assert entry.category == "Equipamentos"
    assert entry.tenant_id == tenant.id
    assert entry.idempotency_key is None  # expenses don't have idempotency keys


# ── Tests: Revenue idempotency ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revenue_idempotency_no_duplicate(db_session: AsyncSession, tenant: Tenant):
    """Calling register_revenue_for_os twice with same key creates only 1 entry."""
    # Use service_order_id=None to avoid FK constraint; key becomes "receita:os:None"
    idempotency_key = "receita:os:None"

    first = await FinancialService.register_revenue_for_os(
        session=db_session,
        tenant_id=tenant.id,
        service_order_id=None,
        amount=Decimal("500.00"),
        os_number=42,
    )
    assert first is not None
    assert first.idempotency_key == idempotency_key

    second = await FinancialService.register_revenue_for_os(
        session=db_session,
        tenant_id=tenant.id,
        service_order_id=None,
        amount=Decimal("500.00"),
        os_number=42,
    )
    assert second is None  # skipped due to idempotency (same key)

    # Verify only one entry exists in DB
    repo = FinancialEntryRepository(db_session)
    found = await repo.get_by_idempotency_key(idempotency_key)
    assert found is not None
    assert found.id == first.id


@pytest.mark.asyncio
async def test_revenue_idempotency_key_format(db_session: AsyncSession, tenant: Tenant):
    """Idempotency key must be receita:os:{service_order_id}."""
    # service_order_id=None → key becomes receita:os:None
    entry = await FinancialService.register_revenue_for_os(
        session=db_session,
        tenant_id=tenant.id,
        service_order_id=None,
        amount=Decimal("100.00"),
        os_number=1,
    )
    assert entry is not None
    assert entry.idempotency_key == "receita:os:None"


# ── Tests: get_summary ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_summary_totals(db_session: AsyncSession, tenant: Tenant):
    svc = FinancialService(db_session)

    # Register revenue directly via repo to avoid FK constraint
    from app.modules.financial.repository import FinancialEntryRepository
    from app.modules.financial.models import EntryType
    from datetime import datetime, timezone
    repo = FinancialEntryRepository(db_session)
    await repo.create(
        tenant_id=tenant.id,
        service_order_id=None,
        entry_type=EntryType.RECEITA,
        amount=Decimal("1000.00"),
        description="OS #1",
        reference_date=datetime.now(timezone.utc),
        idempotency_key="test-sum-receita-1",
    )
    await repo.create(
        tenant_id=tenant.id,
        service_order_id=None,
        entry_type=EntryType.RECEITA,
        amount=Decimal("500.00"),
        description="OS #2",
        reference_date=datetime.now(timezone.utc),
        idempotency_key="test-sum-receita-2",
    )

    # Register expenses
    await svc.register_expense(
        tenant.id,
        FinancialExpenseCreate(
            amount=Decimal("300.00"),
            description="Despesa 1",
            reference_date=datetime.now(timezone.utc),
        ),
    )

    summary = await svc.get_summary(tenant.id)

    assert summary.total_receitas == Decimal("1500.00")
    assert summary.total_despesas == Decimal("300.00")
    assert summary.saldo == Decimal("1200.00")


@pytest.mark.asyncio
async def test_get_summary_empty(db_session: AsyncSession, tenant: Tenant):
    svc = FinancialService(db_session)
    summary = await svc.get_summary(tenant.id)

    assert summary.total_receitas == Decimal("0.00")
    assert summary.total_despesas == Decimal("0.00")
    assert summary.saldo == Decimal("0.00")


# ── Tests: Multi-tenant isolation ─────────────────────────────────────────────

@pytest_asyncio.fixture
async def tenant_b(db_session: AsyncSession) -> Tenant:
    from app.models.tenant import Tenant as TenantModel
    t = TenantModel(
        id=uuid.uuid4(),
        name="Financeira B",
        document="11223344000155",
        email="fin_b@teste.com",
        razao_social="FIN B LTDA",
        nome_fantasia="Financeira B",
        crt="1",
        municipio="São Paulo",
        uf="SP",
        cep="01310100",
        codigo_municipio="3550308",
        logradouro="Rua A",
        numero="1",
        bairro="Centro",
        active=True,
    )
    db_session.add(t)
    await db_session.flush()
    return t


@pytest.mark.asyncio
async def test_multi_tenant_isolation(db_session: AsyncSession, tenant: Tenant, tenant_b: Tenant):
    """Entries from tenant A should not appear in tenant B's list or summary."""
    svc = FinancialService(db_session)

    # Create entry for tenant A (service_order_id=None avoids FK constraint in unit test)
    await FinancialService.register_revenue_for_os(
        session=db_session,
        tenant_id=tenant.id,
        service_order_id=None,
        amount=Decimal("999.00"),
        os_number=99,
    )

    # Tenant B should see nothing
    result_b = await svc.list_entries(tenant_b.id)
    assert result_b.total == 0

    summary_b = await svc.get_summary(tenant_b.id)
    assert summary_b.total_receitas == Decimal("0.00")
    assert summary_b.saldo == Decimal("0.00")
