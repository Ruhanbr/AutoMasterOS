import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.repositories.base_repository import BaseRepository


class TenantRepository(BaseRepository[Tenant]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Tenant, session)

    async def get_by_document(self, document: str) -> Tenant | None:
        stmt = select(Tenant).where(Tenant.document == document)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_id(self, tenant_id: uuid.UUID) -> Tenant | None:
        stmt = select(Tenant).where(Tenant.id == tenant_id, Tenant.active.is_(True))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def document_exists(self, document: str, exclude_id: uuid.UUID | None = None) -> bool:
        # Verifica apenas tenants ATIVOS — soft-deleted não bloqueiam reutilização do CNPJ
        stmt = select(Tenant.id).where(Tenant.document == document, Tenant.active.is_(True))
        if exclude_id:
            stmt = stmt.where(Tenant.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
