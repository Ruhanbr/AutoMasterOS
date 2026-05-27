"""
Serviço de integração com a John Deere Operations Center API.
Gerencia OAuth 2.0, busca de máquinas, alertas e DTCs.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────

SCOPES = "ag1 ag2 eq1 eq2 offline_access openid profile"


# ── Helpers OAuth ─────────────────────────────────────────────────────────────

def build_authorization_url(state: str) -> str:
    """Gera a URL de autorização OAuth para redirecionar o usuário à JD."""
    params = {
        "response_type": "code",
        "client_id": settings.DEERE_CLIENT_ID,
        "redirect_uri": settings.DEERE_REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
    }
    return f"{settings.deere_auth_base}/authorize?{urlencode(params)}"


def generate_state(tenant_id: str) -> str:
    """Gera token CSRF seguro embedando o tenant_id."""
    nonce = secrets.token_hex(16)
    return f"{tenant_id}:{nonce}"


def parse_state(state: str) -> tuple[str, str]:
    """Extrai tenant_id e nonce do state."""
    parts = state.split(":", 1)
    if len(parts) != 2:
        raise ValueError("State inválido")
    return parts[0], parts[1]


# ── Troca de tokens ───────────────────────────────────────────────────────────

async def exchange_code(code: str) -> dict[str, Any]:
    """Troca o authorization code por access_token + refresh_token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.deere_auth_base}/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.DEERE_REDIRECT_URI,
            },
            auth=(settings.DEERE_CLIENT_ID, settings.DEERE_CLIENT_SECRET),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """Renova o access_token usando o refresh_token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.deere_auth_base}/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=(settings.DEERE_CLIENT_ID, settings.DEERE_CLIENT_SECRET),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


def token_expires_at(expires_in: int) -> datetime:
    """Calcula datetime de expiração com 60s de margem."""
    return datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)


# ── Chamadas à API ────────────────────────────────────────────────────────────

def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.deere.axiom.v3+json",
    }


async def get_organizations(access_token: str) -> list[dict]:
    """Lista as organizações John Deere do usuário autenticado."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.deere_api_base}/organizations",
            headers=_headers(access_token),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("values", [])


async def get_machines(access_token: str, org_id: str) -> list[dict]:
    """Lista as máquinas de uma organização JD."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.deere_api_base}/organizations/{org_id}/machines",
            headers=_headers(access_token),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("values", [])


async def get_alerts(access_token: str, org_id: str) -> list[dict]:
    """
    Busca alertas/DTCs ativos de todas as máquinas da organização.
    Retorna lista de alertas com: machineId, dtcCode, severity, description, triggeredAt.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.deere_api_base}/organizations/{org_id}/alerts",
            headers=_headers(access_token),
            params={"embed": "machine"},
            timeout=30,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("values", [])


async def get_machine_hours(access_token: str, machine_id: str) -> dict:
    """Retorna horas de motor de uma máquina específica."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.deere_api_base}/machines/{machine_id}/engineHours",
            headers=_headers(access_token),
            timeout=30,
        )
        if resp.status_code in (404, 204):
            return {}
        resp.raise_for_status()
        return resp.json()
