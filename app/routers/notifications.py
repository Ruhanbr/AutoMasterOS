"""
Router de notificações in-app.

GET  /notifications           → lista (últimas 30) para o usuário logado
GET  /notifications/unread-count → contagem não lidas (para o sino)
POST /notifications/{id}/read → marca uma como lida
POST /notifications/read-all  → marca todas como lidas
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.core.dependencies import CurrentUser, DbSession, TenantId
from app.repositories.notification_repository import NotificationRepository

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    message: str
    link: str | None
    read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UnreadCountOut(BaseModel):
    count: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    session: DbSession,
    current_user: CurrentUser,
    tenant_id: TenantId,
    unread_only: bool = False,
):
    repo = NotificationRepository(session)
    items = await repo.list_for_user(
        user_id=current_user.id,
        tenant_id=tenant_id,
        unread_only=unread_only,
    )
    return [NotificationOut.model_validate(n) for n in items]


@router.get("/unread-count", response_model=UnreadCountOut)
async def unread_count(
    session: DbSession,
    current_user: CurrentUser,
    tenant_id: TenantId,
):
    repo = NotificationRepository(session)
    count = await repo.unread_count(current_user.id, tenant_id)
    return UnreadCountOut(count=count)


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    notification_id: uuid.UUID,
    session: DbSession,
    current_user: CurrentUser,
):
    repo = NotificationRepository(session)
    await repo.mark_read(notification_id, current_user.id)
    await session.commit()


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    session: DbSession,
    current_user: CurrentUser,
    tenant_id: TenantId,
):
    repo = NotificationRepository(session)
    await repo.mark_all_read(current_user.id, tenant_id)
    await session.commit()
