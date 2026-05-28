import uuid

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        type: str,
        title: str,
        message: str,
        link: str | None = None,
    ) -> Notification:
        n = Notification(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            link=link,
        )
        self.session.add(n)
        await self.session.flush()
        return n

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        limit: int = 30,
        unread_only: bool = False,
    ) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.tenant_id == tenant_id,
            )
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        if unread_only:
            stmt = stmt.where(Notification.read.is_(False))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def unread_count(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            Notification.user_id == user_id,
            Notification.tenant_id == tenant_id,
            Notification.read.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
            .values(read=True)
        )

    async def mark_all_read(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.tenant_id == tenant_id,
                Notification.read.is_(False),
            )
            .values(read=True)
        )

    async def get_admins_for_tenant(self, tenant_id: uuid.UUID) -> list[uuid.UUID]:
        """Retorna IDs dos usuários ADMIN do tenant para notificação em massa."""
        from app.models.user import User, UserRole
        stmt = select(User.id).where(
            User.tenant_id == tenant_id,
            User.role == UserRole.ADMIN,
            User.active.is_(True),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
