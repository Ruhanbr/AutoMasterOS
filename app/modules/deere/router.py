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
    """Sincroniza alertas JD do cliente e futuramente cria OS automática."""
    conn = await _get_conn(session, tenant_id, client_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Cliente não conectou a conta John Deere")
    token = await _valid_token(conn, session)
    try:
        alerts = await deere.get_alerts(token, conn.organization_id)
    except Exception as e:
        logger.error("deere_sync_failed", error=str(e))
        raise HTTPException(status_code=502, detail="Erro ao sincronizar")

    for alert in alerts:
        dtc = alert.get("dtcCode") or alert.get("alertType", "UNKNOWN")
        logger.info("deere_alert", client_id=str(client_id), dtc=dtc)
        # TODO: criar OS automática vinculada ao cliente e máquina

    return {
        "alerts_found": len(alerts),
        "message": f"{len(alerts)} alerta(s) encontrado(s).",
    }
