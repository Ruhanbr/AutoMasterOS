import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException
from app.core.logging import get_logger
from app.core.redis_client import cache
from app.modules.financial.models import EntryType, FinancialEntry
from app.modules.financial.repository import FinancialEntryRepository
from app.modules.financial.schemas import (
    FinancialEntryListResponse,
    FinancialEntryResponse,
    FinancialExpenseCreate,
    FinancialSummaryResponse,
)

logger = get_logger(__name__)

_CACHE_TTL     = 120   # 2 min — financeiro muda com frequência
_NS_SUMMARY    = "fin_summary"
_NS_ENTRIES    = "fin_entries"


def _summary_key(tenant_id: uuid.UUID, date_from, date_to, technician_user_id=None) -> str:
    return f"{_NS_SUMMARY}:{tenant_id}:{date_from}:{date_to}:{technician_user_id}"


def _entries_key(tenant_id, entry_type, date_from, date_to, page, page_size, technician_user_id=None) -> str:
    return f"{_NS_ENTRIES}:{tenant_id}:{entry_type}:{date_from}:{date_to}:{page}:{page_size}:{technician_user_id}"


async def _invalidate_tenant_financial_cache(tenant_id: uuid.UUID) -> None:
    """Remove todas as chaves de cache financeiro do tenant."""
    deleted_s = await cache.delete_pattern(f"{_NS_SUMMARY}:{tenant_id}:*")
    deleted_e = await cache.delete_pattern(f"{_NS_ENTRIES}:{tenant_id}:*")
    logger.info(
        "financial_cache_invalidated",
        tenant_id=str(tenant_id),
        summary_keys=deleted_s,
        entries_keys=deleted_e,
    )


class FinancialService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = FinancialEntryRepository(session)

    # ── Receita (chamado pela orquestração, idempotente) ──────────────────────

    @staticmethod
    async def register_revenue_for_os(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        service_order_id: uuid.UUID | None,
        amount: Decimal,
        os_number: int,
    ) -> FinancialEntry | None:
        """
        Cria entrada RECEITA ligada a uma OS.
        Idempotente: retorna None se já existir entrada para a mesma OS.
        Invalida cache financeiro do tenant ao registrar.
        """
        repo = FinancialEntryRepository(session)
        idempotency_key = f"receita:os:{service_order_id}"

        existing = await repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            logger.info(
                "financial_revenue_already_registered",
                service_order_id=str(service_order_id),
                idempotency_key=idempotency_key,
            )
            return None

        entry = await repo.create(
            tenant_id=tenant_id,
            service_order_id=service_order_id,
            entry_type=EntryType.RECEITA,
            amount=amount,
            description=f"Receita da OS #{os_number}",
            category="Serviços e Peças",
            reference_date=datetime.now(timezone.utc),
            idempotency_key=idempotency_key,
        )

        await _invalidate_tenant_financial_cache(tenant_id)

        logger.info(
            "financial_revenue_registered",
            service_order_id=str(service_order_id),
            amount=str(amount),
            entry_id=str(entry.id),
        )
        return entry

    # ── Despesa ───────────────────────────────────────────────────────────────

    async def register_expense(
        self,
        tenant_id: uuid.UUID,
        data: FinancialExpenseCreate,
    ) -> FinancialEntry:
        entry = await self._repo.create(
            tenant_id=tenant_id,
            service_order_id=None,
            entry_type=EntryType.DESPESA,
            amount=data.amount,
            description=data.description,
            category=data.category,
            reference_date=data.reference_date,
            notes=data.notes,
        )

        await _invalidate_tenant_financial_cache(tenant_id)

        logger.info(
            "financial_expense_registered",
            tenant_id=str(tenant_id),
            amount=str(data.amount),
            entry_id=str(entry.id),
        )
        return entry

    # ── List entries com cache Redis ──────────────────────────────────────────

    async def list_entries(
        self,
        tenant_id: uuid.UUID,
        entry_type: EntryType | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
        technician_user_id: uuid.UUID | None = None,
    ) -> FinancialEntryListResponse:
        key = _entries_key(tenant_id, entry_type, date_from, date_to, page, page_size, technician_user_id)
        cached = await cache.get(key)
        if cached is not None:
            logger.info("financial_entries_cache_hit", tenant_id=str(tenant_id), page=page)
            return FinancialEntryListResponse(**cached)

        entries, total = await self._repo.list_by_tenant(
            tenant_id,
            entry_type=entry_type,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
            technician_user_id=technician_user_id,
        )
        pages = max(1, -(-total // page_size))
        result = FinancialEntryListResponse(
            items=[FinancialEntryResponse.model_validate(e) for e in entries],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

        await cache.set(key, result.model_dump(), ttl=_CACHE_TTL)
        return result

    # ── Summary com cache Redis ───────────────────────────────────────────────

    async def get_summary(
        self,
        tenant_id: uuid.UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        technician_user_id: uuid.UUID | None = None,
    ) -> FinancialSummaryResponse:
        key = _summary_key(tenant_id, date_from, date_to, technician_user_id)
        cached = await cache.get(key)
        if cached is not None:
            logger.info("financial_summary_cache_hit", tenant_id=str(tenant_id))
            return FinancialSummaryResponse(**cached)

        summary = await self._repo.get_summary(
            tenant_id, date_from=date_from, date_to=date_to, technician_user_id=technician_user_id
        )
        result = FinancialSummaryResponse(**summary)

        await cache.set(key, result.model_dump(), ttl=_CACHE_TTL)
        return result
