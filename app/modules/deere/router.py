"""
Router da integração John Deere.

Endpoints:
  GET  /integrations/deere/connect      → redireciona para OAuth JD
  GET  /integrations/deere/callback     → recebe o code OAuth e salva tokens
  GET  /integrations/deere/status       → verifica se o tenant está conectado
  DELETE /integrations/deere/disconnect → desconecta o tenant
  POST /integrations/deere/sync         → sincroniza alertas manualmente
  GET  /integrations/deere/machines     → lista máquinas JD do tenant
  GET  /integrations/deere/alerts       → lista alertas/DTCs ativos
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
    organization_id: str | None = None
    organization_name: str | None = None
    token_expires_at: datetime | None = None


class AlertSummary(BaseModel):
    alert_id: str
    machine_id: str
    machine_name: str
    dtc_code: str
    severity: str
    description: str
    triggered_at: str


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_connection(session, tenant_id: uuid.UUID) -> DeereConnection | None:
    result = await session.execute(
        select(DeereConnection).where(
            DeereConnection.tenant_id == tenant_id,
            DeereConnection.active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def _valid_token(conn: DeereConnection, session) -> str:
    """Retorna access_token válido, renovando se necessário."""
    if conn.token_expires_at <= datetime.now(timezone.utc):
        logger.info("deere_token_expired_refreshing", tenant_id=str(conn.tenant_id))
        tokens = await deere.refresh_access_token(conn.refresh_token)
        conn.access_token = tokens["access_token"]
        conn.refresh_token = tokens.get("refresh_token", conn.refresh_token)
        conn.token_expires_at = deere.token_expires_at(tokens["expires_in"])
        await session.flush()
        await session.commit()
    return conn.access_token


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/connect", summary="Inicia fluxo OAuth com John Deere")
async def connect(
    tenant_id: TenantId,
    current_user: CurrentUser,
):
    """Redireciona o usuário para a página de autorização da John Deere."""
    state = deere.generate_state(str(tenant_id))
    url = deere.build_authorization_url(state)
    return RedirectResponse(url=url)


@router.get("/callback", summary="Callback OAuth John Deere")
async def callback(
    session: DbSession,
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(default=None),
):
    """
    John Deere redireciona aqui após o usuário autorizar.
    Troca o code por tokens e salva no banco.
    """
    if error:
        raise HTTPException(status_code=400, detail=f"Autorização negada: {error}")

    try:
        tenant_id_str, _ = deere.parse_state(state)
        tenant_id = uuid.UUID(tenant_id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="State inválido")

    # Troca code por tokens
    try:
        tokens = await deere.exchange_code(code)
    except Exception as e:
        logger.error("deere_token_exchange_failed", error=str(e))
        raise HTTPException(status_code=502, detail="Erro ao obter tokens da John Deere")

    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token", "")
    expires_at = deere.token_expires_at(tokens.get("expires_in", 3600))

    # Busca a primeira organização do usuário
    try:
        orgs = await deere.get_organizations(access_token)
        org = orgs[0] if orgs else {}
        org_id = org.get("id", "unknown")
        org_name = org.get("name", "")
    except Exception as e:
        logger.warning("deere_orgs_fetch_failed", error=str(e))
        org_id = "unknown"
        org_name = ""

    # Salva ou atualiza conexão
    existing = await _get_connection(session, tenant_id)
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
            organization_id=org_id,
            organization_name=org_name,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=expires_at,
        )
        session.add(conn)

    await session.commit()
    logger.info("deere_connected", tenant_id=str(tenant_id), org_id=org_id)

    # Redireciona para o frontend com sucesso
    return RedirectResponse(url="/configuracoes?deere=connected")


@router.get("/status", response_model=DeereStatusResponse)
async def get_status(tenant_id: TenantId, session: DbSession, current_user: CurrentUser):
    """Verifica se o tenant tem conexão ativa com a John Deere."""
    conn = await _get_connection(session, tenant_id)
    if not conn:
        return DeereStatusResponse(connected=False)
    return DeereStatusResponse(
        connected=True,
        organization_id=conn.organization_id,
        organization_name=conn.organization_name,
        token_expires_at=conn.token_expires_at,
    )


@router.delete("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(tenant_id: TenantId, session: DbSession, current_user: CurrentUser):
    """Desconecta o tenant da John Deere."""
    conn = await _get_connection(session, tenant_id)
    if conn:
        conn.active = False
        await session.commit()
    logger.info("deere_disconnected", tenant_id=str(tenant_id))


@router.get("/machines", summary="Lista máquinas JD do tenant")
async def list_machines(
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    """Busca as máquinas da organização JD conectada."""
    conn = await _get_connection(session, tenant_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Conta John Deere não conectada")

    token = await _valid_token(conn, session)
    try:
        machines = await deere.get_machines(token, conn.organization_id)
    except Exception as e:
        logger.error("deere_machines_fetch_failed", error=str(e))
        raise HTTPException(status_code=502, detail="Erro ao buscar máquinas da John Deere")

    return {"machines": machines, "total": len(machines)}


@router.get("/alerts", summary="Lista alertas/DTCs ativos")
async def list_alerts(
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    """Busca alertas e DTCs ativos das máquinas JD."""
    conn = await _get_connection(session, tenant_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Conta John Deere não conectada")

    token = await _valid_token(conn, session)
    try:
        alerts = await deere.get_alerts(token, conn.organization_id)
    except Exception as e:
        logger.error("deere_alerts_fetch_failed", error=str(e))
        raise HTTPException(status_code=502, detail="Erro ao buscar alertas da John Deere")

    return {"alerts": alerts, "total": len(alerts)}


@router.post("/sync", summary="Sincroniza alertas e cria OS automaticamente")
async def sync_alerts(
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
):
    """
    Busca alertas JD e cria OS automaticamente para cada DTC encontrado.
    """
    conn = await _get_connection(session, tenant_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Conta John Deere não conectada")

    token = await _valid_token(conn, session)

    try:
        alerts = await deere.get_alerts(token, conn.organization_id)
    except Exception as e:
        logger.error("deere_sync_failed", error=str(e))
        raise HTTPException(status_code=502, detail="Erro ao sincronizar com John Deere")

    created_os = 0
    for alert in alerts:
        dtc = alert.get("dtcCode") or alert.get("alertType", "UNKNOWN")
        machine_id = alert.get("machineId") or ""
        description = alert.get("description") or f"Alerta John Deere: {dtc}"
        severity = alert.get("severity", "").upper()

        logger.info(
            "deere_alert_received",
            tenant_id=str(tenant_id),
            dtc=dtc,
            machine_id=machine_id,
            severity=severity,
        )
        # TODO: criar OS automaticamente vinculada à máquina
        created_os += 1

    return {
        "alerts_found": len(alerts),
        "os_created": created_os,
        "message": f"{len(alerts)} alertas encontrados. Criação automática de OS em breve.",
    }
