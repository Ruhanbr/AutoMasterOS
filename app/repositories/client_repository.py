import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.repositories.base_repository import BaseRepository


class ClientRepository(BaseRepository[Client]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Client, session)

    async def get_by_id_and_tenant(
        self, client_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Client | None:
        stmt = select(Client).where(
            Client.id == client_id,
            Client.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_document_and_tenant(
        self, document: str, tenant_id: uuid.UUID
    ) -> Client | None:
        stmt = select(Client).where(
            Client.document == document,
            Client.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def document_exists_in_tenant(
        self,
        document: str,
        tenant_id: uuid.UUID,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        stmt = select(Client.id).where(
            Client.document == document,
            Client.tenant_id == tenant_id,
        )
        if exclude_id:
            stmt = stmt.where(Client.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_by_tenant(
        self,
        tenant_id: uuid.UUID,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Client], int]:
        filters = [Client.tenant_id == tenant_id]
        if active_only:
            filters.append(Client.active.is_(True))
        return await self.list_paginated(*filters, page=page, page_size=page_size)

    async def search_by_name(
        self, tenant_id: uuid.UUID, name: str, page: int = 1, page_size: int = 20
    ) -> tuple[list[Client], int]:
        filters = [
            Client.tenant_id == tenant_id,
            Client.name.ilike(f"%{name}%"),
        ]
        return await self.list_paginated(*filters, page=page, page_size=page_size)
