import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateResourceException, ResourceNotFoundException
from app.core.logging import get_logger
from app.models.tenant import Tenant
from app.repositories.tenant_repository import TenantRepository
from app.schemas.tenant import TenantCreate, TenantUpdate

logger = get_logger(__name__)


class TenantService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = TenantRepository(session)

    async def create(self, data: TenantCreate) -> Tenant:
        if await self._repo.document_exists(data.document):
            raise DuplicateResourceException("Tenant", "document", data.document)

        tenant = await self._repo.create(**data.model_dump())
        logger.info("tenant_criado", tenant_id=str(tenant.id), document=data.document)
        return tenant

    async def get(self, tenant_id: uuid.UUID) -> Tenant:
        tenant = await self._repo.get_active_by_id(tenant_id)
        if tenant is None:
            raise ResourceNotFoundException("Tenant", str(tenant_id))
        return tenant

    async def update(self, tenant_id: uuid.UUID, data: TenantUpdate) -> Tenant:
        tenant = await self.get(tenant_id)
        update_data = data.model_dump(exclude_unset=True)

        # Verifica unicidade de CNPJ se foi alterado
        new_document = update_data.get("document")
        if new_document and new_document != tenant.document:
            if await self._repo.document_exists(new_document):
                raise DuplicateResourceException("Tenant", "document", new_document)

        for field, value in update_data.items():
            setattr(tenant, field, value)
        updated = await self._repo.save(tenant)
        logger.info("tenant_atualizado", tenant_id=str(tenant_id))
        return updated

    async def delete(self, tenant_id: uuid.UUID) -> None:
        """
        Soft-delete: marca a oficina e todos os seus usuários como inativos.
        Isso libera os e-mails para reutilização em novos cadastros.
        """
        from sqlalchemy import update as sa_update
        from app.models.user import User

        tenant = await self.get(tenant_id)
        tenant.active = False
        await self._repo.save(tenant)

        # Desativa todos os usuários do tenant em lote
        await self._repo.session.execute(
            sa_update(User)
            .where(User.tenant_id == tenant_id)
            .values(active=False)
        )
        logger.info("tenant_desativado", tenant_id=str(tenant_id))
