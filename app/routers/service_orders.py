import uuid
from datetime import date

from fastapi import APIRouter, Body, HTTPException, Query, status
from app.models.service_order import ServiceOrder

from app.core.authorization import get_os_tenant_filter
from app.core.dependencies import CurrentUser, DbSession, TenantId
from app.core.exceptions import AutoMasterException, to_http_exception
from app.models.service_order import ServiceOrderStatus
from app.models.user import UserRole
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.service_order import (
    SendBudgetRequest,
    ServiceOrderCreate,
    ServiceOrderDatesUpdate,
    ServiceOrderItemCreate,
    ServiceOrderItemResponse,
    ServiceOrderResponse,
    ServiceOrderStatusUpdate,
    ServiceOrderSummary,
    ServiceOrderUpdate,
)
from app.services.service_order_service import ServiceOrderService

router = APIRouter(prefix="/service-orders", tags=["service-orders"])


@router.post("/", response_model=ServiceOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_service_order(
    data: ServiceOrderCreate,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    try:
        # TECNICO fica vinculado automaticamente à OS que ele mesmo cria
        created_by = current_user.id if current_user.role == UserRole.TECNICO else None
        order = await ServiceOrderService(session).create(
            tenant_id, data, created_by_user_id=created_by
        )
        return ServiceOrderResponse.model_validate(order)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.get("/", response_model=PaginatedResponse)
async def list_service_orders(
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    status: ServiceOrderStatus | None = Query(None),
    client_id: uuid.UUID | None = Query(None),
    machine_id: uuid.UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    try:
        os_filter = get_os_tenant_filter(current_user)
        result = await ServiceOrderService(session).list(
            tenant_id,
            status=status,
            client_id=client_id,
            machine_id=machine_id,
            technician_user_id=os_filter.get("technician_user_id"),
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
        return PaginatedResponse(
            items=[ServiceOrderSummary.model_validate(o) for o in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
            pages=result.pages,
        )
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.get("/summary", response_model=dict)
async def get_service_orders_summary(
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    status: ServiceOrderStatus | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
):
    """Retorna totais agregados para o relatório de OS por período."""
    return await ServiceOrderService(session).summary(
        tenant_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/{order_id}", response_model=ServiceOrderResponse)
async def get_service_order(
    order_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    try:
        order = await ServiceOrderService(session).get(tenant_id, order_id)
        # TECNICO só vê OS vinculadas a ele — 404 evita information disclosure
        if (
            current_user.role == UserRole.TECNICO
            and order.technician_user_id != current_user.id
        ):
            raise HTTPException(status_code=404, detail="Ordem de Serviço não encontrada.")
        return ServiceOrderResponse.model_validate(order)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.patch("/{order_id}", response_model=ServiceOrderResponse)
async def update_service_order(
    order_id: uuid.UUID,
    data: ServiceOrderUpdate,
    tenant_id: TenantId,
    session: DbSession,
):
    try:
        order = await ServiceOrderService(session).update(tenant_id, order_id, data)
        return ServiceOrderResponse.model_validate(order)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.patch("/{order_id}/dates", response_model=ServiceOrderResponse)
async def update_dates(
    order_id: uuid.UUID,
    data: ServiceOrderDatesUpdate,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    try:
        order = await ServiceOrderService(session).update_dates(tenant_id, order_id, data)
        return ServiceOrderResponse.model_validate(order)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.patch("/{order_id}/status", response_model=ServiceOrderResponse)
async def update_status(
    order_id: uuid.UUID,
    data: ServiceOrderStatusUpdate,
    tenant_id: TenantId,
    session: DbSession,
):
    try:
        order = await ServiceOrderService(session).update_status(
            tenant_id, order_id, data.status, data.notes
        )
        return ServiceOrderResponse.model_validate(order)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.post(
    "/{order_id}/finalize",
    response_model=ServiceOrderResponse,
    summary="Finaliza a OS e dispara emissão automática da NF-e",
)
async def finalize_service_order(
    order_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    notes: str | None = Body(None, embed=True),
):
    """
    Finaliza a Ordem de Serviço e dispara automaticamente a emissão da NF-e.

    - A NF-e é gerada de forma **assíncrona** via Celery.
    - O endpoint retorna imediatamente com a OS no status `FINALIZADA`.
    - Acompanhe o status da NF-e em `GET /invoices/service-order/{order_id}`.
    """
    try:
        order = await ServiceOrderService(session).finalize(tenant_id, order_id, notes)
        return ServiceOrderResponse.model_validate(order)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.post("/{order_id}/items", response_model=ServiceOrderResponse, status_code=status.HTTP_201_CREATED)
async def add_item(
    order_id: uuid.UUID,
    data: ServiceOrderItemCreate,
    tenant_id: TenantId,
    session: DbSession,
):
    try:
        order = await ServiceOrderService(session).add_item(tenant_id, order_id, data)
        return ServiceOrderResponse.model_validate(order)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.delete("/{order_id}/items/{item_id}", response_model=ServiceOrderResponse)
async def remove_item(
    order_id: uuid.UUID,
    item_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
):
    try:
        order = await ServiceOrderService(session).remove_item(tenant_id, order_id, item_id)
        return ServiceOrderResponse.model_validate(order)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


# ── Portal do Cliente ─────────────────────────────────────────────────────────

@router.post(
    "/{order_id}/send-budget",
    response_model=ServiceOrderResponse,
    summary="Enviar orçamento para aprovação do cliente",
    description="Muda o status do orçamento para AGUARDANDO_APROVACAO e retorna o link público.",
)
async def send_budget(
    order_id: uuid.UUID,
    data: SendBudgetRequest,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    from datetime import datetime, timezone
    from app.models.service_order import BudgetStatus
    from sqlalchemy import select as sa_select

    result = await session.execute(
        sa_select(ServiceOrder)
        .where(ServiceOrder.id == order_id, ServiceOrder.tenant_id == tenant_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="OS não encontrada.")

    if order.budget_status == BudgetStatus.APROVADO:
        raise HTTPException(status_code=409, detail="Orçamento já foi aprovado pelo cliente.")

    order.budget_status = BudgetStatus.AGUARDANDO_APROVACAO
    order.budget_sent_at = datetime.now(timezone.utc)
    # Garante que o token existe (OS criadas antes da migration podem não ter)
    if not order.public_token:
        import uuid as _uuid
        order.public_token = str(_uuid.uuid4())

    session.add(order)
    await session.commit()
    await session.refresh(order)
    return ServiceOrderResponse.model_validate(order)


@router.get(
    "/{order_id}/portal-link",
    summary="Obter link público do portal do cliente",
)
async def get_portal_link(
    order_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    from sqlalchemy import select as sa_select
    from app.core.config import settings

    result = await session.execute(
        sa_select(ServiceOrder)
        .where(ServiceOrder.id == order_id, ServiceOrder.tenant_id == tenant_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="OS não encontrada.")

    if not order.public_token:
        import uuid as _uuid
        order.public_token = str(_uuid.uuid4())
        session.add(order)
        await session.commit()
        await session.refresh(order)

    # A URL base do frontend vem de variável de ambiente ou fallback
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    portal_url = f"{frontend_url}/os/{order.public_token}"

    return {
        "portal_url": portal_url,
        "public_token": order.public_token,
        "budget_status": order.budget_status,
        "os_number": order.number,
    }
