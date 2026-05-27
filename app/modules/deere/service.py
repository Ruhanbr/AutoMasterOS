"""
Serviço de integração com a John Deere Operations Center API.
Gerencia OAuth 2.0, busca de máquinas, alertas e DTCs por cliente.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SCOPES = "ag1 ag2 eq1 eq2 offline_access openid profile"


# ── OAuth helpers ─────────────────────────────────────────────────────────────

def build_authorization_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.DEERE_CLIENT_ID,
        "redirect_uri": settings.DEERE_REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
    }
    return f"{settings.deere_auth_base}/authorize?{urlencode(params)}"


def generate_state(tenant_id: str, client_id: str) -> str:
    """State embute tenant_id e client_id separados por ':' + nonce CSRF."""
    nonce = secrets.token_hex(16)
    return f"{tenant_id}:{client_id}:{nonce}"


def parse_state(state: str) -> tuple[str, str]:
    """Extrai (tenant_id, client_id) do state."""
    parts = state.split(":")
    if len(parts) < 3:
        raise ValueError("State inválido")
    return parts[0], parts[1]


def token_expires_at(expires_in: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)


# ── Troca de tokens ───────────────────────────────────────────────────────────

async def exchange_code(code: str) -> dict[str, Any]:
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


# ── Chamadas à API ────────────────────────────────────────────────────────────

def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.deere.axiom.v3+json",
    }


async def get_organizations(access_token: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.deere_api_base}/organizations",
            headers=_headers(access_token),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("values", [])


async def get_machines(access_token: str, org_id: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.deere_api_base}/organizations/{org_id}/machines",
            headers=_headers(access_token),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("values", [])


async def get_alerts(access_token: str, org_id: str) -> list[dict]:
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
        return resp.json().get("values", [])


async def get_machine_hours(access_token: str, machine_id: str) -> dict:
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
