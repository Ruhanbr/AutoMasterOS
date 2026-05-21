import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.financial.models import EntryType, FinancialEntry
from app.repositories.base_repository import BaseRepository


class FinancialEntryRepository(BaseRepository[FinancialEntry]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(FinancialEntry, session)

    async def get_by_idempotency_key(self, key: str) -> FinancialEntry | None:
        stmt = select(FinancialEntry).where(FinancialEntry.idempotency_key == key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: uuid.UUID,
        entry_type: EntryType | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
        technician_user_id: uuid.UUID | None = None,
    ) -> tuple[list[FinancialEntry], int]:
        from app.models.service_order import ServiceOrder

        filters = [FinancialEntry.tenant_id == tenant_id]
        if entry_type is not None:
            filters.append(FinancialEntry.entry_type == entry_type)
        if date_from is not None:
            filters.append(FinancialEntry.reference_date >= date_from)
        if date_to is not None:
            filters.append(FinancialEntry.reference_date <= date_to)

        if technician_user_id is not None:
            # TECNICO vê apenas entradas vinculadas às suas próprias OS
            # (entradas sem service_order_id são invisíveis — são despesas globais da oficina)
            filters.append(
                FinancialEntry.service_order_id.in_(
                    select(ServiceOrder.id).where(
                        ServiceOrder.tenant_id == tenant_id,
                        ServiceOrder.technician_user_id == technician_user_id,
                    )
                )
            )

        return await self.list_paginated(
            *filters,
            page=page,
            page_size=page_size,
            order_by=FinancialEntry.reference_date.desc(),
        )

    async def get_summary(
        self,
        tenant_id: uuid.UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        technician_user_id: uuid.UUID | None = None,
    ) -> dict:
        """Returns total_receitas, total_despesas, saldo."""
        from app.models.service_order import ServiceOrder

        base_filters = [FinancialEntry.tenant_id == tenant_id]
        if date_from is not None:
            base_filters.append(FinancialEntry.reference_date >= date_from)
        if date_to is not None:
            base_filters.append(FinancialEntry.reference_date <= date_to)
        if technician_user_id is not None:
            base_filters.append(
                FinancialEntry.service_order_id.in_(
                    select(ServiceOrder.id).where(
                        ServiceOrder.tenant_id == tenant_id,
                        ServiceOrder.technician_user_id == technician_user_id,
                    )
                )
            )

        # Receitas
        receita_stmt = (
            select(func.coalesce(func.sum(FinancialEntry.amount), Decimal("0.00")))
            .where(*base_filters)
            .where(FinancialEntry.entry_type == EntryType.RECEITA)
        )
        # Despesas
        despesa_stmt = (
            select(func.coalesce(func.sum(FinancialEntry.amount), Decimal("0.00")))
            .where(*base_filters)
            .where(FinancialEntry.entry_type == EntryType.DESPESA)
        )

        total_receitas = (await self.session.execute(receita_stmt)).scalar_one() or Decimal("0.00")
        total_despesas = (await self.session.execute(despesa_stmt)).scalar_one() or Decimal("0.00")

        return {
            "total_receitas": Decimal(str(total_receitas)),
            "total_despesas": Decimal(str(total_despesas)),
            "saldo": Decimal(str(total_receitas)) - Decimal(str(total_despesas)),
            "date_from": date_from,
            "date_to": date_to,
        }
