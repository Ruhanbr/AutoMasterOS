"""
Portal Público — endpoints acessados pelo cliente sem autenticação.

Usa apenas o public_token da OS como controle de acesso.
Não expõe dados sensíveis do tenant, financeiro ou outros clientes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.dependencies import DbSession
from app.models.service_order import BudgetStatus, ServiceOrder
from app.models.tenant import Tenant
from app.schemas.service_order import (
    BudgetDecisionRequest,
    PublicServiceOrderResponse,
    ServiceOrderItemResponse,
)

router = APIRouter(prefix="/public", tags=["portal-cliente"])


async def _get_os_by_token(token: str, session) -> ServiceOrder:
    """Busca a OS pelo public_token ou lança 404."""
    result = await session.execute(
        select(ServiceOrder).where(ServiceOrder.public_token == token)
    )
    os = result.scalar_one_or_none()
    if not os:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ordem de serviço não encontrada.",
        )
    return os


def _build_response(os: ServiceOrder, tenant: Tenant | None) -> PublicServiceOrderResponse:
    """Monta a resposta pública sem dados sensíveis."""
    client_name = None
    if os.client:
        client_name = os.client.name

    machine_info = None
    if os.machine:
        parts = [
            os.machine.brand or "",
            os.machine.model or "",
            str(os.machine.year) if os.machine.year else "",
        ]
        machine_info = " ".join(p for p in parts if p).strip() or None

    return PublicServiceOrderResponse(
        number=os.number,
        status=os.status,
        budget_status=os.budget_status,
        description=os.description,
        diagnosis=os.diagnosis,
        technician_name=os.technician_name,
        opened_at=os.opened_at,
        expected_delivery_at=os.expected_delivery_at,
        budget_sent_at=os.budget_sent_at,
        budget_approved_at=os.budget_approved_at,
        budget_rejected_at=os.budget_rejected_at,
        budget_rejection_reason=os.budget_rejection_reason,
        client_viewed_at=os.client_viewed_at,
        total_services=os.total_services,
        total_parts=os.total_parts,
        total_displacement=os.total_displacement,
        total_discount=os.total_discount,
        total_amount=os.total_amount,
        items=[ServiceOrderItemResponse.model_validate(i) for i in os.items],
        client_name=client_name,
        machine_info=machine_info,
        workshop_name=tenant.name if tenant else None,
        workshop_phone=getattr(tenant, "phone", None),
        budget_signature=os.budget_signature,
        budget_signer_name=os.budget_signer_name,
        budget_signer_document=os.budget_signer_document,
    )


# ── GET /public/os/{token} ────────────────────────────────────────────────────

@router.get(
    "/os/{token}",
    response_model=PublicServiceOrderResponse,
    summary="Portal do Cliente — visualizar OS",
    description="Retorna os dados públicos da OS. Registra a primeira visualização do cliente.",
)
async def get_public_order(token: str, session: DbSession):
    os = await _get_os_by_token(token, session)

    # Registra primeira visualização
    if os.client_viewed_at is None:
        os.client_viewed_at = datetime.now(timezone.utc)
        session.add(os)
        await session.commit()
        await session.refresh(os)

    # Busca dados da oficina (tenant)
    tenant_result = await session.execute(
        select(Tenant).where(Tenant.id == os.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()

    return _build_response(os, tenant)


# ── POST /public/os/{token}/approve ──────────────────────────────────────────

@router.post(
    "/os/{token}/approve",
    response_model=PublicServiceOrderResponse,
    summary="Portal do Cliente — aprovar orçamento com assinatura digital",
)
async def approve_budget(token: str, data: BudgetDecisionRequest, request: Request, session: DbSession):
    os = await _get_os_by_token(token, session)

    if os.budget_status != BudgetStatus.AGUARDANDO_APROVACAO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Este orçamento não está aguardando aprovação (status atual: {os.budget_status}).",
        )

    # Captura IP real (considera proxies/load balancers)
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.headers.get("X-Real-IP")
        or (request.client.host if request.client else None)
    )

    now = datetime.now(timezone.utc)
    os.budget_status = BudgetStatus.APROVADO
    os.budget_approved_at = now
    os.budget_signer_name = data.signer_name
    os.budget_signer_document = data.signer_document
    os.budget_signature = data.signature
    os.budget_signer_ip = client_ip
    if os.client_viewed_at is None:
        os.client_viewed_at = now

    session.add(os)
    await session.commit()
    await session.refresh(os)

    tenant_result = await session.execute(select(Tenant).where(Tenant.id == os.tenant_id))
    tenant = tenant_result.scalar_one_or_none()

    return _build_response(os, tenant)


# ── POST /public/os/{token}/reject ───────────────────────────────────────────

@router.post(
    "/os/{token}/reject",
    response_model=PublicServiceOrderResponse,
    summary="Portal do Cliente — recusar orçamento",
)
async def reject_budget(token: str, data: BudgetDecisionRequest, session: DbSession):
    os = await _get_os_by_token(token, session)

    if os.budget_status != BudgetStatus.AGUARDANDO_APROVACAO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Este orçamento não está aguardando aprovação (status atual: {os.budget_status}).",
        )

    now = datetime.now(timezone.utc)
    os.budget_status = BudgetStatus.RECUSADO
    os.budget_rejected_at = now
    os.budget_rejection_reason = data.reason
    if os.client_viewed_at is None:
        os.client_viewed_at = now

    session.add(os)
    await session.commit()
    await session.refresh(os)

    tenant_result = await session.execute(select(Tenant).where(Tenant.id == os.tenant_id))
    tenant = tenant_result.scalar_one_or_none()

    return _build_response(os, tenant)
