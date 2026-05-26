"""
Machines Router — com isolamento por cliente (X-Cliente-ID).

Isolamento em duas camadas:
  1. Tenant (sempre) — extraído do JWT, nunca by-passável
  2. Cliente (quando X-Cliente-ID presente) — filtra para o dono da máquina

Comportamento por endpoint:
  GET /             → sem X-Cliente-ID: todas do tenant (admin)
                      com X-Cliente-ID: apenas do cliente informado
  GET /{id}         → sem X-Cliente-ID: checa só tenant (admin)
                      com X-Cliente-ID: checa tenant + ownership (→ 403)
  GET /client/{id}  → sempre filtra por client_id + tenant_id
  GET /{id}/os      → histórico paginado + cache Redis (N+1 free)
  POST /            → cria máquina para o client_id do body
  PATCH /{id}       → update com SELECT FOR UPDATE
  DELETE /{id}      → soft-delete (active=False)
"""

import uuid

from fastapi import APIRouter, Header, Query, status

from app.core.dependencies import ClientId, CurrentUser, DbSession, TenantId
from app.core.exceptions import AutoMasterException, to_http_exception
from app.schemas.common import PaginatedResponse
from app.schemas.machine import MachineCreate, MachineResponse, MachineUpdate
from app.services.machine_service import MachineService

router = APIRouter(prefix="/machines", tags=["machines"])


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=MachineResponse, status_code=status.HTTP_201_CREATED)
async def create_machine(
    data: MachineCreate,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
):
    try:
        machine = await MachineService(session).create(
            tenant_id, data, idempotency_key=x_idempotency_key
        )
        return MachineResponse.model_validate(machine)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


# ── List (com isolamento por X-Cliente-ID) ────────────────────────────────────

@router.get("/", response_model=PaginatedResponse)
async def list_machines(
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    client_id: ClientId,                         # None sem header, UUID com header
    active_only: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    Lista máquinas com isolamento automático por X-Cliente-ID.

    - SEM header → retorna todas do tenant (uso administrativo)
    - COM header → retorna APENAS as do cliente informado (portal cliente)
    """
    try:
        result = await MachineService(session).list(
            tenant_id,
            client_id=client_id,   # None → tenant-wide; UUID → client-scoped
            active_only=active_only,
            page=page,
            page_size=page_size,
        )
        return PaginatedResponse(
            items=[MachineResponse.model_validate(m) for m in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
            pages=result.pages,
        )
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.get("/client/{client_id}", response_model=PaginatedResponse)
async def list_machines_by_client(
    client_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Lista máquinas de um cliente específico (sempre filtrado por tenant + client)."""
    try:
        result = await MachineService(session).list(
            tenant_id,
            client_id=client_id,
            page=page,
            page_size=page_size,
        )
        return PaginatedResponse(
            items=[MachineResponse.model_validate(m) for m in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
            pages=result.pages,
        )
    except AutoMasterException as exc:
        raise to_http_exception(exc)


# ── Get (com ownership check por X-Cliente-ID) ────────────────────────────────

@router.get("/{machine_id}", response_model=MachineResponse)
async def get_machine(
    machine_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    client_id: ClientId,   # None = admin; UUID = client ownership enforced
):
    """
    Retorna máquina.

    - SEM X-Cliente-ID → checa apenas tenant (uso administrativo)
    - COM X-Cliente-ID → checa tenant + client_id; 403 se não for dono
    """
    try:
        svc = MachineService(session)
        if client_id is not None:
            # Modo cliente: ownership obrigatório
            machine = await svc.get_for_client(tenant_id, machine_id, client_id)
        else:
            # Modo admin: apenas tenant check
            machine = await svc.get(tenant_id, machine_id)
        return MachineResponse.model_validate(machine)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{machine_id}", response_model=MachineResponse)
async def update_machine(
    machine_id: uuid.UUID,
    data: MachineUpdate,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    try:
        machine = await MachineService(session).update_with_lock(tenant_id, machine_id, data)
        return MachineResponse.model_validate(machine)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


# ── Histórico OS (paginado + selectinload + cache Redis) ──────────────────────

@router.get("/{machine_id}/os/summary", response_model=dict)
async def get_machine_os_summary(
    machine_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    client_id: ClientId,
    status: str | None = Query(None),
):
    """Totais financeiros e contagem por status do histórico de OS de uma máquina."""
    try:
        svc = MachineService(session)
        if client_id is not None:
            await svc.get_for_client(tenant_id, machine_id, client_id)
        else:
            await svc.get(tenant_id, machine_id)
        return await svc.os_summary_for_machine(
            tenant_id=tenant_id,
            machine_id=machine_id,
            status=status,
        )
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.get("/{machine_id}/os", response_model=PaginatedResponse)
async def list_machine_service_orders(
    machine_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    client_id: ClientId,
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """
    Histórico de OS paginado com selectinload (N+1 free) + cache Redis 5 min.

    COM X-Cliente-ID → 403 se a máquina não pertencer ao cliente.
    """
    try:
        svc = MachineService(session)
        if client_id is not None:
            await svc.get_for_client(tenant_id, machine_id, client_id)
        else:
            await svc.get(tenant_id, machine_id)
        return await svc.list_os_historico_cached(
            tenant_id=tenant_id,
            machine_id=machine_id,
            status=status,
            page=page,
            page_size=page_size,
        )
    except AutoMasterException as exc:
        raise to_http_exception(exc)


# ── Reactivate ───────────────────────────────────────────────────────────────

@router.post("/{machine_id}/reactivate", response_model=MachineResponse)
async def reactivate_machine(
    machine_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    """Reativa uma máquina previamente desativada."""
    try:
        machine = await MachineService(session).reactivate(tenant_id, machine_id)
        return MachineResponse.model_validate(machine)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


# ── Delete (soft) ─────────────────────────────────────────────────────────────

@router.delete("/{machine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_machine(
    machine_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    try:
        await MachineService(session).deactivate(tenant_id, machine_id)
    except AutoMasterException as exc:
        raise to_http_exception(exc)
