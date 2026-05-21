import uuid

from fastapi import APIRouter, Query, status

from app.core.dependencies import DbSession, TenantId
from app.core.exceptions import AutoMasterException, to_http_exception
from app.schemas.client import ClientCreate, ClientResponse, ClientUpdate
from app.schemas.common import MessageResponse, PaginatedResponse
from app.services.client_service import ClientService

router = APIRouter(prefix="/clients", tags=["clients"])


@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    data: ClientCreate,
    tenant_id: TenantId,
    session: DbSession,
):
    try:
        client = await ClientService(session).create(tenant_id, data)
        return ClientResponse.model_validate(client)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.get("/", response_model=PaginatedResponse)
async def list_clients(
    tenant_id: TenantId,
    session: DbSession,
    active_only: bool = Query(True),
    name: str | None = Query(None, description="Filtro parcial por nome"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    try:
        result = await ClientService(session).list(
            tenant_id,
            active_only=active_only,
            name=name,
            page=page,
            page_size=page_size,
        )
        return PaginatedResponse(
            items=[ClientResponse.model_validate(c) for c in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
            pages=result.pages,
        )
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
):
    try:
        client = await ClientService(session).get(tenant_id, client_id)
        return ClientResponse.model_validate(client)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: uuid.UUID,
    data: ClientUpdate,
    tenant_id: TenantId,
    session: DbSession,
):
    try:
        client = await ClientService(session).update(tenant_id, client_id, data)
        return ClientResponse.model_validate(client)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.post("/{client_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_client_post(
    client_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
):
    """POST /clients/{id}/deactivate → 204. Soft-delete via POST para compatibilidade."""
    try:
        await ClientService(session).deactivate(tenant_id, client_id)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.delete("/{client_id}", response_model=MessageResponse)
async def deactivate_client(
    client_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
):
    try:
        await ClientService(session).deactivate(tenant_id, client_id)
        return MessageResponse(message="Cliente desativado com sucesso")
    except AutoMasterException as exc:
        raise to_http_exception(exc)
