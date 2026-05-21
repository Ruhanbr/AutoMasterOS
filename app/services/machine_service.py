import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleException,
    ClientOwnershipException,
    DuplicateResourceException,
    ResourceNotFoundException,
)
from app.core.logging import get_logger
from app.core.redis_client import cache
from app.models.machine import Machine
from app.repositories.client_repository import ClientRepository
from app.repositories.machine_repository import MachineRepository
from app.repositories.service_order_repository import ServiceOrderRepository
from app.schemas.common import PaginatedResponse
from app.schemas.machine import MachineCreate, MachineUpdate

logger = get_logger(__name__)

_CACHE_TTL = 300   # 5 minutos
_CACHE_NS  = "machine_os"


class MachineService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo        = MachineRepository(session)
        self._client_repo = ClientRepository(session)
        self._so_repo     = ServiceOrderRepository(session)

    # ── Create ────────────────────────────────────────────────────────────────

    async def create(
        self,
        tenant_id: uuid.UUID,
        data: MachineCreate,
        idempotency_key: str | None = None,
    ) -> Machine:
        if idempotency_key:
            existing = await self._repo.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                logger.info(
                    "maquina_idempotente",
                    machine_id=str(existing.id),
                    idempotency_key=idempotency_key,
                )
                return existing

        client = await self._client_repo.get_by_id_and_tenant(data.client_id, tenant_id)
        if client is None:
            raise ResourceNotFoundException("Cliente", str(data.client_id))
        if not client.active:
            raise ValueError("Não é possível cadastrar máquina para cliente inativo")

        if await self._repo.serial_exists_for_tenant(data.serial_number, tenant_id):
            raise DuplicateResourceException("Máquina", "serial_number", data.serial_number)

        machine = await self._repo.create(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            **data.model_dump(),
        )
        logger.info(
            "maquina_criada",
            machine_id=str(machine.id),
            client_id=str(data.client_id),
            serial=data.serial_number,
        )
        return machine

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_for_client(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        client_id: uuid.UUID,
    ) -> Machine:
        """
        Busca máquina validando ownership client_id + tenant_id.

        Levanta ClientOwnershipException (→ HTTP 403) se a máquina não
        pertencer ao cliente, sem revelar se ela existe para outros.
        """
        machine = await self._repo.get_by_id_client_and_tenant(
            machine_id, client_id, tenant_id
        )
        if machine is None:
            raise ClientOwnershipException("Máquina", str(machine_id))
        return machine

    async def get(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> Machine:
        machine = await self._repo.get_by_id_and_tenant(machine_id, tenant_id)
        if machine is None:
            raise ResourceNotFoundException("Máquina", str(machine_id))
        return machine

    async def list(
        self,
        tenant_id: uuid.UUID,
        client_id: uuid.UUID | None = None,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        if client_id:
            items, total = await self._repo.list_by_client(
                client_id, tenant_id, active_only=active_only, page=page, page_size=page_size
            )
        else:
            items, total = await self._repo.list_by_tenant(
                tenant_id, active_only=active_only, page=page, page_size=page_size
            )
        return PaginatedResponse.build(items, total, page, page_size)

    # ── Histórico OS com Redis cache + selectinload (N+1 free) ───────────────

    async def list_os_historico_cached(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        """
        Retorna OS paginadas de uma máquina com selectinload em itens/cliente.

        Estratégia de cache:
          - Chave: machine_os:{tenant_id}:{machine_id}:{page}:{page_size}
          - TTL: 5 min
          - Invalidado ao finalizar/criar OS (via _invalidate_machine_os_cache)
        """
        cache_key = f"{_CACHE_NS}:{tenant_id}:{machine_id}:{page}:{page_size}"
        cached = await cache.get(cache_key)
        if cached is not None:
            logger.info(
                "machine_os_cache_hit",
                machine_id=str(machine_id),
                page=page,
            )
            return PaginatedResponse(**cached)

        orders, total = await self._so_repo.list_by_machine_with_items(
            machine_id=machine_id,
            tenant_id=tenant_id,
            page=page,
            page_size=page_size,
        )

        from app.schemas.service_order import ServiceOrderSummary

        total_pages = max(1, (total + page_size - 1) // page_size)
        result = PaginatedResponse(
            items=[ServiceOrderSummary.model_validate(o) for o in orders],
            total=total,
            page=page,
            page_size=page_size,
            pages=total_pages,
        )

        await cache.set(cache_key, result.model_dump(), ttl=_CACHE_TTL)
        logger.info(
            "machine_os_cache_miss",
            machine_id=str(machine_id),
            page=page,
            total=total,
        )
        return result

    @staticmethod
    async def invalidate_machine_os_cache(
        tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> None:
        """Chamado ao criar/finalizar OS — invalida todas as páginas da máquina."""
        pattern = f"{_CACHE_NS}:{tenant_id}:{machine_id}:*"
        deleted = await cache.delete_pattern(pattern)
        logger.info(
            "machine_os_cache_invalidated",
            machine_id=str(machine_id),
            keys_deleted=deleted,
        )

    # ── Update ────────────────────────────────────────────────────────────────

    async def update(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, data: MachineUpdate
    ) -> Machine:
        machine = await self.get(tenant_id, machine_id)

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(machine, field, value)

        updated = await self._repo.save(machine)
        logger.info("maquina_atualizada", machine_id=str(machine_id))
        return updated

    async def update_with_lock(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, data: MachineUpdate
    ) -> Machine:
        """Concurrency-safe update using SELECT FOR UPDATE."""
        from app.core.exceptions import ConcurrencyConflictException  # noqa: F401

        machine = await self._repo.get_by_id_and_tenant_with_lock(machine_id, tenant_id)
        if machine is None:
            raise ResourceNotFoundException("Máquina", str(machine_id))

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(machine, field, value)

        updated = await self._repo.save(machine)
        logger.info("maquina_atualizada_com_lock", machine_id=str(machine_id))
        return updated

    # ── Reactivate ────────────────────────────────────────────────────────────

    async def reactivate(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> Machine:
        machine = await self._repo.get_by_id_and_tenant_any_status(machine_id, tenant_id)
        if machine is None:
            raise ResourceNotFoundException("Máquina", str(machine_id))
        machine.active = True
        machine.deleted_at = None
        updated = await self._repo.save(machine)
        logger.info("maquina_reativada", machine_id=str(machine_id))
        return updated

    # ── Deactivate ────────────────────────────────────────────────────────────

    async def deactivate(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> Machine:
        machine = await self.get(tenant_id, machine_id)

        if await self._repo.has_active_service_orders(machine.id):
            raise BusinessRuleException(
                "Máquina possui OS ativas e não pode ser removida"
            )

        machine.active = False
        machine.deleted_at = datetime.now(timezone.utc)
        updated = await self._repo.save(machine)
        logger.info("maquina_desativada", machine_id=str(machine_id))
        return updated
