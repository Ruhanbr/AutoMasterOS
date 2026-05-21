import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CurrentUser, DbSession, TenantId
from app.core.exceptions import to_http_exception, AutoMasterException
from app.modules.stock.schemas import (
    StockItemCreate,
    StockItemListResponse,
    StockItemResponse,
    StockItemUpdate,
    StockMovementCreate,
    StockMovementResponse,
)
from app.modules.stock.service import StockService

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("", response_model=StockItemListResponse)
async def list_stock_items(
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> StockItemListResponse:
    try:
        svc = StockService(session)
        return await svc.list_items(tenant_id, page=page, page_size=page_size)
    except AutoMasterException as e:
        raise to_http_exception(e)


@router.post("", response_model=StockItemResponse, status_code=201)
async def create_stock_item(
    data: StockItemCreate,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
) -> StockItemResponse:
    try:
        svc = StockService(session)
        item = await svc.create_item(tenant_id, data)
        return StockItemResponse.model_validate(item)
    except AutoMasterException as e:
        raise to_http_exception(e)


@router.get("/{item_id}", response_model=StockItemResponse)
async def get_stock_item(
    item_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
) -> StockItemResponse:
    try:
        svc = StockService(session)
        item = await svc.get_item(tenant_id, item_id)
        return StockItemResponse.model_validate(item)
    except AutoMasterException as e:
        raise to_http_exception(e)


@router.put("/{item_id}", response_model=StockItemResponse)
async def update_stock_item(
    item_id: uuid.UUID,
    data: StockItemUpdate,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
) -> StockItemResponse:
    try:
        svc = StockService(session)
        item = await svc.update_item(tenant_id, item_id, data)
        return StockItemResponse.model_validate(item)
    except AutoMasterException as e:
        raise to_http_exception(e)


@router.delete("/{item_id}", status_code=204)
async def delete_stock_item(
    item_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
) -> None:
    try:
        svc = StockService(session)
        await svc.delete_item(tenant_id, item_id)
    except AutoMasterException as e:
        raise to_http_exception(e)


@router.post("/{item_id}/movements", response_model=StockMovementResponse, status_code=201)
async def add_movement(
    item_id: uuid.UUID,
    data: StockMovementCreate,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
) -> StockMovementResponse:
    try:
        svc = StockService(session)
        movement = await svc.add_movement(tenant_id, item_id, data)
        return StockMovementResponse.model_validate(movement)
    except AutoMasterException as e:
        raise to_http_exception(e)


@router.get("/{item_id}/movements", response_model=list[StockMovementResponse])
async def list_movements(
    item_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> list[StockMovementResponse]:
    try:
        svc = StockService(session)
        movements, _ = await svc.list_movements(tenant_id, item_id, page=page, page_size=page_size)
        return [StockMovementResponse.model_validate(m) for m in movements]
    except AutoMasterException as e:
        raise to_http_exception(e)
