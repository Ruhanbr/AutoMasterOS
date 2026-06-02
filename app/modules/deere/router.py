"""
Router da integração John Deere — por cliente (fazendeiro).

Endpoints:
  GET  /integrations/deere/connect?client_id=xxx  → inicia OAuth para o cliente
  GET  /integrations/deere/callback               → recebe code e salva tokens
  GET  /integrations/deere/clients/{id}/status    → status da conexão do cliente
  DELETE /integrations/deere/clients/{id}/disconnect
  GET  /integrations/deere/clients/{id}/machines  → máquinas JD do cliente
  GET  /integrations/deere/clients/{id}/alerts    → DTCs/alertas do cliente
  POST /integrations/deere/clients/{id}/sync      → sincroniza e cria OS
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession, TenantId
from app.core.logging import get_logger
from app.modules.deere import service as deere
from app.modules.deere.models import DeereConnection

logger = get_logger(__name__)

router = APIRouter(prefix="/integrations/deere", tags=["John Deere"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class DeereStatusResponse(BaseModel):
    connected: bool
    client_id: str | None = None
    organization_id: str | None = None
    organization_name: str | None = None
    token_expires_at: datetime | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_conn(session, tenant_id: uuid.UUID, client_id: uuid.UUID) -> DeereConnection | None:
    result = await session.execute(
        select(DeereConnection).where(
            DeereConnection.tenant_id == tenant_id,
            DeereConnection.client_id == client_id,
            DeereConnection.active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def _valid_token(conn: DeereConnection, session) -> str:
    """Retorna access_token válido, renovando se necessário."""
    if conn.token_expires_at <= datetime.now(timezone.utc):
        tokens = await deere.refresh_access_token(conn.refresh_token)
        conn.access_token = tokens["access_token"]
        conn.refresh_token = tokens.get("refresh_token", conn.refresh_token)
        conn.token_expires_at = deere.token_expires_at(tokens["expires_in"])
        await session.flush()
        await session.commit()
    return conn.access_token


# ── OAuth ─────────────────────────────────────────────────────────────────────

@router.get("/connect-url", summary="Retorna a URL OAuth JD para o frontend redirecionar")
async def get_connect_url(
    tenant_id: TenantId,
    current_user: CurrentUser,
    client_id: uuid.UUID = Query(..., description="ID do cliente (fazendeiro)"),
):
    """
    Retorna a URL de autorização OAuth da John Deere.
    O frontend faz a chamada autenticada e depois redireciona o browser.
    """
    state = deere.generate_state(str(tenant_id), str(client_id))
    url = deere.build_authorization_url(state)
    return {"url": url}


@router.get("/connect", summary="Inicia OAuth JD para um cliente específico")
async def connect(
    tenant_id: TenantId,
    current_user: CurrentUser,
    client_id: uuid.UUID = Query(..., description="ID do cliente (fazendeiro)"),
):
    """Gera URL OAuth e redireciona para a John Deere."""
    state = deere.generate_state(str(tenant_id), str(client_id))
    url = deere.build_authorization_url(state)
    return RedirectResponse(url=url)


@router.get("/callback", summary="Callback OAuth John Deere")
async def callback(
    session: DbSession,
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(default=None),
):
    if error:
        raise HTTPException(status_code=400, detail=f"Autorização negada: {error}")

    try:
        tenant_id_str, client_id_str = deere.parse_state(state)
        tenant_id = uuid.UUID(tenant_id_str)
        client_id = uuid.UUID(client_id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="State inválido")

    try:
        tokens = await deere.exchange_code(code)
    except Exception as e:
        logger.error("deere_token_exchange_failed", error=str(e))
        raise HTTPException(status_code=502, detail="Erro ao obter tokens da John Deere")

    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token", "")
    expires_at = deere.token_expires_at(tokens.get("expires_in", 3600))

    try:
        orgs = await deere.get_organizations(access_token)
        org = orgs[0] if orgs else {}
        org_id = org.get("id", "unknown")
        org_name = org.get("name", "")
    except Exception as e:
        logger.warning("deere_orgs_fetch_failed", error=str(e))
        org_id = "unknown"
        org_name = ""

    existing = await _get_conn(session, tenant_id, client_id)
    if existing:
        existing.access_token = access_token
        existing.refresh_token = refresh_token
        existing.token_expires_at = expires_at
        existing.organization_id = org_id
        existing.organization_name = org_name
        existing.active = True
    else:
        conn = DeereConnection(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            client_id=client_id,
            organization_id=org_id,
            organization_name=org_name,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=expires_at,
        )
        session.add(conn)

    await session.commit()
    logger.info("deere_client_connected", tenant_id=str(tenant_id), client_id=str(client_id))

    # Redireciona para a ficha do cliente com flag de sucesso
    return RedirectResponse(url=f"/clients?deere_client={client_id}&deere=connected")


# ── Endpoints por cliente ─────────────────────────────────────────────────────

@router.get("/clients/{client_id}/status", response_model=DeereStatusResponse)
async def client_status(
    client_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    conn = await _get_conn(session, tenant_id, client_id)
    if not conn:
        return DeereStatusResponse(connected=False, client_id=str(client_id))
    return DeereStatusResponse(
        connected=True,
        client_id=str(client_id),
        organization_id=conn.organization_id,
        organization_name=conn.organization_name,
        token_expires_at=conn.token_expires_at,
    )


@router.delete("/clients/{client_id}/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def client_disconnect(
    client_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    conn = await _get_conn(session, tenant_id, client_id)
    if conn:
        conn.active = False
        await session.commit()
    logger.info("deere_client_disconnected", client_id=str(client_id))


@router.get("/clients/{client_id}/machines")
async def client_machines(
    client_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    conn = await _get_conn(session, tenant_id, client_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Cliente não conectou a conta John Deere")
    token = await _valid_token(conn, session)
    try:
        machines = await deere.get_machines(token, conn.organization_id)
    except Exception as e:
        logger.error("deere_machines_failed", error=str(e))
        raise HTTPException(status_code=502, detail="Erro ao buscar máquinas")
    return {"machines": machines, "total": len(machines)}


@router.get("/clients/{client_id}/alerts")
async def client_alerts(
    client_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    conn = await _get_conn(session, tenant_id, client_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Cliente não conectou a conta John Deere")
    token = await _valid_token(conn, session)
    try:
        alerts = await deere.get_alerts(token, conn.organization_id)
    except Exception as e:
        logger.error("deere_alerts_failed", error=str(e))
        raise HTTPException(status_code=502, detail="Erro ao buscar alertas")
    return {"alerts": alerts, "total": len(alerts)}


@router.post("/clients/{client_id}/sync")
async def client_sync(
    client_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    """Sincroniza alertas JD do cliente, cria OS automáticas e notifica gestores."""
    conn = await _get_conn(session, tenant_id, client_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Cliente não conectou a conta John Deere")
    token = await _valid_token(conn, session)
    try:
        alerts = await deere.get_alerts(token, conn.organization_id)
    except Exception as e:
        logger.error("deere_sync_failed", error=str(e))
        raise HTTPException(status_code=502, detail="Erro ao sincronizar")

    os_criadas = await _create_os_from_alerts(session, tenant_id, client_id, alerts)

    return {
        "alerts_found": len(alerts),
        "os_created": os_criadas,
        "message": f"{len(alerts)} alerta(s) encontrado(s), {os_criadas} OS criada(s).",
    }


async def _create_os_from_alerts(
    session,
    tenant_id: uuid.UUID,
    client_id: uuid.UUID,
    alerts: list[dict],
) -> int:
    """
    Para cada alerta JD:
      1. Cria uma OS com status ABERTA, descrevendo o DTC
      2. Notifica todos os ADMINs do tenant
    Retorna a quantidade de OS criadas.
    """
    if not alerts:
        return 0

    from datetime import datetime, timezone
    from sqlalchemy import select, func as sqlfunc
    from app.models.service_order import ServiceOrder, ServiceOrderStatus, BudgetStatus
    from app.models.machine import Machine
    from app.models.client import Client
    from app.repositories.notification_repository import NotificationRepository
    from app.models.notification import NotificationType

    # Busca o nome do cliente
    client_result = await session.execute(
        select(Client.name).where(Client.id == client_id)
    )
    client_name = client_result.scalar_one_or_none() or "Cliente"

    # Carrega todas as máquinas ativas do cliente indexadas por serial_number (upper)
    machines_result = await session.execute(
        select(Machine).where(
            Machine.client_id == client_id,
            Machine.tenant_id == tenant_id,
            Machine.deleted_at.is_(None),
        )
    )
    machines_by_serial: dict[str, Machine] = {
        m.serial_number.upper(): m
        for m in machines_result.scalars().all()
        if m.serial_number
    }

    # Próximo número de OS para o tenant
    num_result = await session.execute(
        select(sqlfunc.coalesce(sqlfunc.max(ServiceOrder.number), 0)).where(
            ServiceOrder.tenant_id == tenant_id
        )
    )
    next_number = (num_result.scalar_one() or 0) + 1

    notif_repo = NotificationRepository(session)
    admin_ids = await notif_repo.get_admins_for_tenant(tenant_id)

    os_criadas = 0
    for alert in alerts:
        dtc = alert.get("dtcCode") or alert.get("alertType") or "ALERTA"
        description_raw = alert.get("description") or alert.get("alertType") or dtc
        severity = alert.get("severity", "")

        # Tenta cruzar a máquina JD com o cadastro AutoMaster via serial_number
        jd_machine: dict = alert.get("machine") or {}
        jd_serial: str = (jd_machine.get("serialNumber") or jd_machine.get("vin") or "").upper()
        matched_machine: Machine | None = machines_by_serial.get(jd_serial)

        machine_line = ""
        if matched_machine:
            machine_line = f"Máquina: {matched_machine.brand} {matched_machine.model} · S/N {matched_machine.serial_number}\n"
        elif jd_machine.get("name") or jd_serial:
            machine_line = f"Máquina JD: {jd_machine.get('name', '')} · S/N {jd_serial or 'N/A'}\n"

        description = (
            f"[John Deere — Automático]\n"
            f"Código: {dtc}\n"
            f"Descrição: {description_raw}\n"
            f"Severidade: {severity or 'N/A'}\n"
            f"{machine_line}"
        )

        os = ServiceOrder(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            client_id=client_id,
            machine_id=matched_machine.id if matched_machine else None,
            number=next_number,
            status=ServiceOrderStatus.ABERTA,
            description=description,
            opened_at=datetime.now(timezone.utc),
            public_token=str(uuid.uuid4()),
            budget_status=BudgetStatus.RASCUNHO,
        )
        session.add(os)
        await session.flush()

        # Mensagem da notificação indica se a máquina foi identificada
        machine_info = (
            f" — {matched_machine.brand} {matched_machine.model}"
            if matched_machine
            else (f" — máquina S/N {jd_serial}" if jd_serial else "")
        )
        for admin_id in admin_ids:
            await notif_repo.create(
                tenant_id=tenant_id,
                user_id=admin_id,
                type=NotificationType.JD_ALERT,
                title=f"⚠️ Alerta JD — {dtc}",
                message=f"Nova OS #{next_number} para {client_name}{machine_info}. {description_raw}",
                link=f"/service-orders/{os.id}",
            )

        next_number += 1
        os_criadas += 1
        logger.info(
            "deere_os_criada",
            os_id=str(os.id),
            client_id=str(client_id),
            dtc=dtc,
            machine_id=str(matched_machine.id) if matched_machine else None,
            serial_matched=bool(matched_machine),
        )

    await session.commit()
    return os_criadas
