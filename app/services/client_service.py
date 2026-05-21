import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    TenantMismatchException,
)
from app.core.logging import get_logger
from app.models.client import Client
from app.repositories.client_repository import ClientRepository
from app.repositories.tenant_repository import TenantRepository
from app.schemas.client import ClientCreate, ClientUpdate
from app.schemas.common import PaginatedResponse

logger = get_logger(__name__)


class ClientService:
    """
    Toda lógica de negócio de clientes.
    Nunca acessa o banco diretamente — delega ao repository.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = ClientRepository(session)
        self._tenant_repo = TenantRepository(session)

    async def create(self, tenant_id: uuid.UUID, data: ClientCreate) -> Client:
        await self._assert_tenant_active(tenant_id)

        if await self._repo.document_exists_in_tenant(data.document, tenant_id):
            raise DuplicateResourceException("Cliente", "document", data.document)

        client = await self._repo.create(
            tenant_id=tenant_id,
            **data.model_dump(),
        )
        logger.info(
            "cliente_criado",
            client_id=str(client.id),
            tenant_id=str(tenant_id),
            document=data.document,
        )
        return client

    async def get(self, tenant_id: uuid.UUID, client_id: uuid.UUID) -> Client:
        client = await self._repo.get_by_id_and_tenant(client_id, tenant_id)
        if client is None:
            raise ResourceNotFoundException("Cliente", str(client_id))
        return client

    async def list(
        self,
        tenant_id: uuid.UUID,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 20,
        name: str | None = None,
    ) -> PaginatedResponse:
        if name:
            items, total = await self._repo.search_by_name(
                tenant_id, name, page=page, page_size=page_size
            )
        else:
            items, total = await self._repo.list_by_tenant(
                tenant_id, active_only=active_only, page=page, page_size=page_size
            )
        return PaginatedResponse.build(items, total, page, page_size)

    async def update(
        self, tenant_id: uuid.UUID, client_id: uuid.UUID, data: ClientUpdate
    ) -> Client:
        client = await self.get(tenant_id, client_id)

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(client, field, value)

        updated = await self._repo.save(client)
        logger.info("cliente_atualizado", client_id=str(client_id), tenant_id=str(tenant_id))
        return updated

    async def deactivate(self, tenant_id: uuid.UUID, client_id: uuid.UUID) -> Client:
        client = await self.get(tenant_id, client_id)
        client.active = False
        updated = await self._repo.save(client)
        logger.info("cliente_desativado", client_id=str(client_id), tenant_id=str(tenant_id))
        return updated

    async def _assert_tenant_active(self, tenant_id: uuid.UUID) -> None:
        tenant = await self._tenant_repo.get_active_by_id(tenant_id)
        if tenant is None:
            raise ResourceNotFoundException("Tenant", str(tenant_id))
