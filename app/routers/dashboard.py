"""
Dashboard — endpoint único que retorna todos os agregados para a tela inicial.
Evita múltiplas chamadas do frontend.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select, and_

from app.core.dependencies import CurrentUser, DbSession, TenantId
from app.models.client import Client
from app.models.service_order import ServiceOrder, ServiceOrderStatus
from app.modules.financial.models import FinancialEntry, EntryType
from app.modules.stock.models import StockItem

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class MonthlyRevenue(BaseModel):
    month: str          # "Jan", "Fev" …
    year: int
    receitas: float
    despesas: float


class OsStatusCount(BaseModel):
    status: str
    count: int


class TopClient(BaseModel):
    name: str
    total: float
    os_count: int


class LowStockItem(BaseModel):
    id: str
    name: str
    sku: str
    quantity: float
    min_quantity: float


class DashboardResponse(BaseModel):
    # KPIs financeiros
    receita_mes_atual: float
    receita_mes_anterior: float
    despesa_mes_atual: float
    saldo_mes_atual: float
    ticket_medio: float

    # OS
    os_abertas: int
    os_em_andamento: int
    os_finalizadas: int

    # Gráficos
    receita_mensal: list[MonthlyRevenue]    # últimos 6 meses
    os_por_status: list[OsStatusCount]

    # Rankings
    top_clientes: list[TopClient]           # top 5
    estoque_critico: list[LowStockItem]     # abaixo do mínimo


# ── Helpers ───────────────────────────────────────────────────────────────────

_MES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
           "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _d(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(Decimal(str(v)))
    except Exception:
        return 0.0


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
) -> DashboardResponse:
    now = datetime.now(timezone.utc)
    cur_year, cur_month = now.year, now.month

    # ── OS por status ──────────────────────────────────────────────────────
    os_counts_result = await session.execute(
        select(ServiceOrder.status, func.count(ServiceOrder.id).label("cnt"))
        .where(ServiceOrder.tenant_id == tenant_id)
        .group_by(ServiceOrder.status)
    )
    os_counts: dict[str, int] = {}
    for row in os_counts_result.all():
        key = row.status.value if hasattr(row.status, "value") else str(row.status)
        os_counts[key] = row.cnt

    os_abertas       = os_counts.get("ABERTA", 0)
    os_em_andamento  = os_counts.get("EM_ANDAMENTO", 0)
    os_finalizadas   = os_counts.get("FINALIZADA", 0)

    os_por_status = [
        OsStatusCount(status="Abertas",       count=os_abertas),
        OsStatusCount(status="Em Andamento",  count=os_em_andamento),
        OsStatusCount(status="Finalizadas",   count=os_finalizadas),
        OsStatusCount(status="Canceladas",    count=os_counts.get("CANCELADA", 0)),
    ]

    # ── Ticket médio (OS finalizadas) ─────────────────────────────────────
    ticket_result = await session.execute(
        select(func.avg(ServiceOrder.total_amount))
        .where(
            ServiceOrder.tenant_id == tenant_id,
            ServiceOrder.status == ServiceOrderStatus.FINALIZADA,
            ServiceOrder.total_amount.isnot(None),
        )
    )
    ticket_medio = _d(ticket_result.scalar())

    # ── Receita/despesa mensal — últimos 6 meses ──────────────────────────
    # Gera lista dos últimos 6 meses (ano, mês)
    months: list[tuple[int, int]] = []
    y, m = cur_year, cur_month
    for _ in range(6):
        months.insert(0, (y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    fin_result = await session.execute(
        select(
            func.extract("year",  FinancialEntry.reference_date).label("yr"),
            func.extract("month", FinancialEntry.reference_date).label("mo"),
            FinancialEntry.entry_type,
            func.sum(FinancialEntry.amount).label("total"),
        )
        .where(
            FinancialEntry.tenant_id == tenant_id,
            FinancialEntry.reference_date >= datetime(months[0][0], months[0][1], 1, tzinfo=timezone.utc),
        )
        .group_by("yr", "mo", FinancialEntry.entry_type)
    )

    fin_map: dict[tuple[int,int], dict[str, float]] = {}
    for row in fin_result.all():
        key = (int(row.yr), int(row.mo))
        etype = row.entry_type.value if hasattr(row.entry_type, "value") else str(row.entry_type)
        fin_map.setdefault(key, {"RECEITA": 0.0, "DESPESA": 0.0})
        fin_map[key][etype] = _d(row.total)

    receita_mensal = [
        MonthlyRevenue(
            month=_MES_PT[mo - 1],
            year=yr,
            receitas=fin_map.get((yr, mo), {}).get("RECEITA", 0.0),
            despesas=fin_map.get((yr, mo), {}).get("DESPESA", 0.0),
        )
        for yr, mo in months
    ]

    # KPIs do mês atual e anterior
    cur_data  = fin_map.get((cur_year, cur_month), {})
    prev_m    = cur_month - 1 or 12
    prev_y    = cur_year if cur_month > 1 else cur_year - 1
    prev_data = fin_map.get((prev_y, prev_m), {})

    receita_mes_atual    = cur_data.get("RECEITA", 0.0)
    despesa_mes_atual    = cur_data.get("DESPESA", 0.0)
    receita_mes_anterior = prev_data.get("RECEITA", 0.0)
    saldo_mes_atual      = receita_mes_atual - despesa_mes_atual

    # ── Top 5 clientes por receita ────────────────────────────────────────
    top_result = await session.execute(
        select(
            Client.name,
            func.sum(ServiceOrder.total_amount).label("total"),
            func.count(ServiceOrder.id).label("os_count"),
        )
        .join(Client, ServiceOrder.client_id == Client.id)
        .where(
            ServiceOrder.tenant_id == tenant_id,
            ServiceOrder.status == ServiceOrderStatus.FINALIZADA,
            ServiceOrder.total_amount.isnot(None),
        )
        .group_by(Client.id, Client.name)
        .order_by(func.sum(ServiceOrder.total_amount).desc())
        .limit(5)
    )
    top_clientes = [
        TopClient(name=row.name, total=_d(row.total), os_count=row.os_count)
        for row in top_result.all()
    ]

    # ── Estoque crítico (qty <= min_quantity) ─────────────────────────────
    stock_result = await session.execute(
        select(StockItem)
        .where(
            StockItem.tenant_id == tenant_id,
            StockItem.active.is_(True),
            StockItem.quantity <= StockItem.min_quantity,
        )
        .order_by(StockItem.quantity)
        .limit(8)
    )
    estoque_critico = [
        LowStockItem(
            id=str(item.id),
            name=item.description,
            sku=item.sku or "—",
            quantity=_d(item.quantity),
            min_quantity=_d(item.min_quantity),
        )
        for item in stock_result.scalars().all()
    ]

    return DashboardResponse(
        receita_mes_atual=receita_mes_atual,
        receita_mes_anterior=receita_mes_anterior,
        despesa_mes_atual=despesa_mes_atual,
        saldo_mes_atual=saldo_mes_atual,
        ticket_medio=ticket_medio,
        os_abertas=os_abertas,
        os_em_andamento=os_em_andamento,
        os_finalizadas=os_finalizadas,
        receita_mensal=receita_mensal,
        os_por_status=os_por_status,
        top_clientes=top_clientes,
        estoque_critico=estoque_critico,
    )
