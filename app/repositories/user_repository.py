"""
UserRepository — acesso ao banco para entidades User.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email_and_tenant(
        self, email: str, tenant_id: uuid.UUID
    ) -> User | None:
        result = await self._session.execute(
            select(User).where(
                User.email == email,
                User.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> User:
        user = User(**kwargs)
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def get_by_name_and_tenant(
        self, full_name: str, tenant_id: uuid.UUID
    ) -> User | None:
        """Busca técnico pelo nome completo dentro do tenant (case-insensitive)."""
        result = await self._session.execute(
            select(User).where(
                User.full_name.ilike(full_name),
                User.tenant_id == tenant_id,
                User.active.is_(True),
            )
        )
        return result.scalars().first()

    async def list_by_tenant(
        self,
        tenant_id: uuid.UUID,
        role: UserRole | None = None,
        active_only: bool = True,
    ) -> list[User]:
        q = select(User).where(User.tenant_id == tenant_id)
        if active_only:
            q = q.where(User.active.is_(True))
        if role is not None:
            q = q.where(User.role == role)
        q = q.order_by(User.full_name)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def save(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def get_super_admin_by_email(self, email: str) -> User | None:
        """Busca usuário SUPER_ADMIN pelo email (sem filtro de tenant)."""
        result = await self._session.execute(
            select(User).where(
                User.email == email,
                User.role == UserRole.SUPER_ADMIN,
                User.active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_email_global(self, email: str) -> User | None:
        """Busca usuário por email em qualquer tenant (para forgot-password)."""
        result = await self._session.execute(
            select(User).where(User.email == email, User.active.is_(True))
        )
        return result.scalars().first()
