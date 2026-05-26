import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.authorization import get_os_tenant_filter
from app.core.dependencies import CurrentUser, DbSession, TenantId, require_role
from app.core.exceptions import AutoMasterException, to_http_exception
from app.models.user import UserRole
from app.modules.financial.models import EntryType
from app.modules.financial.schemas import (
    FinancialEntryListResponse,
    FinancialEntryResponse,
    FinancialExpenseCreate,
    FinancialSummaryResponse,
)
from app.modules.financial.service import FinancialService

router = APIRouter(prefix="/financial", tags=["financial"])


@router.get("", response_model=FinancialEntryListResponse)
async def list_financial_entries(
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    entry_type: Optional[EntryType] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    technician_user_id: Optional[uuid.UUID] = Query(None, description="Filtrar por técnico (apenas ADMIN)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> FinancialEntryListResponse:
    try:
        # TECNICO vê apenas lançamentos vinculados às suas próprias OS
        os_filter = get_os_tenant_filter(current_user)
        effective_technician = os_filter.get("technician_user_id") or technician_user_id

        svc = FinancialService(session)
        return await svc.list_entries(
            tenant_id,
            entry_type=entry_type,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
            technician_user_id=effective_technician,
        )
    except AutoMasterException as e:
        raise to_http_exception(e)


@router.post(
    "/expenses",
    response_model=FinancialEntryResponse,
    status_code=201,
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.TECNICO))],
)
async def register_expense(
    data: FinancialExpenseCreate,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
) -> FinancialEntryResponse:
    try:
        svc = FinancialService(session)
        entry = await svc.register_expense(tenant_id, data)
        return FinancialEntryResponse.model_validate(entry)
    except AutoMasterException as e:
        raise to_http_exception(e)


@router.get("/summary", response_model=FinancialSummaryResponse)
async def get_financial_summary(
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    technician_user_id: Optional[uuid.UUID] = Query(None, description="Filtrar por técnico (apenas ADMIN)"),
) -> FinancialSummaryResponse:
    try:
        # TECNICO vê apenas resumo dos seus próprios lançamentos
        os_filter = get_os_tenant_filter(current_user)
        effective_technician = os_filter.get("technician_user_id") or technician_user_id

        svc = FinancialService(session)
        return await svc.get_summary(
            tenant_id,
            date_from=date_from,
            date_to=date_to,
            technician_user_id=effective_technician,
        )
    except AutoMasterException as e:
        raise to_http_exception(e)
