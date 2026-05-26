import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.machine import Machine
from app.repositories.base_repository import BaseRepository


class MachineRepository(BaseRepository[Machine]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Machine, session)

    async def get_by_id_and_tenant(
        self, machine_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Machine | None:
        stmt = select(Machine).where(
            Machine.id == machine_id,
            Machine.tenant_id == tenant_id,
            Machine.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_client_and_tenant(
        self,
        machine_id: uuid.UUID,
        client_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Machine | None:
        """
        Busca máquina filtrando por TODAS as três chaves:
        machine_id + client_id + tenant_id.

        Retorna None se a máquina não existir OU não pertencer ao cliente —
        nunca vaza informação sobre a existência do recurso.
        Usa o índice composto ix_machines_client_tenant.
        """
        stmt = select(Machine).where(
            Machine.id == machine_id,
            Machine.client_id == client_id,
            Machine.tenant_id == tenant_id,
            Machine.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_and_tenant_with_lock(
        self, machine_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Machine | None:
        """FOR UPDATE lock for concurrency control."""
        stmt = (
            select(Machine)
            .where(
                Machine.id == machine_id,
                Machine.tenant_id == tenant_id,
                Machine.deleted_at.is_(None),
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_serial_number(self, serial_number: str) -> Machine | None:
        stmt = select(Machine).where(Machine.serial_number == serial_number)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def serial_exists(
        self, serial_number: str, exclude_id: uuid.UUID | None = None
    ) -> bool:
        stmt = select(Machine.id).where(Machine.serial_number == serial_number)
        if exclude_id:
            stmt = stmt.where(Machine.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def serial_exists_for_tenant(
        self, serial_number: str, tenant_id: uuid.UUID, exclude_id: uuid.UUID | None = None
    ) -> bool:
        """Tenant-scoped serial number uniqueness check."""
        stmt = select(Machine.id).where(
            Machine.serial_number == serial_number,
            Machine.tenant_id == tenant_id,
            Machine.deleted_at.is_(None),
        )
        if exclude_id:
            stmt = stmt.where(Machine.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_by_idempotency_key(self, key: str) -> Machine | None:
        stmt = select(Machine).where(Machine.idempotency_key == key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_and_tenant_any_status(
        self, machine_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Machine | None:
        """Busca máquina incluindo inativas/desativadas (sem filtro deleted_at)."""
        stmt = select(Machine).where(
            Machine.id == machine_id,
            Machine.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def has_active_service_orders(self, machine_id: uuid.UUID) -> bool:
        """Check if machine has any non-FINALIZADA service orders."""
        from app.models.service_order import ServiceOrder, ServiceOrderStatus

        stmt = (
            select(ServiceOrder.id)
            .where(
                ServiceOrder.machine_id == machine_id,
                ServiceOrder.status != ServiceOrderStatus.FINALIZADA,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_by_tenant(
        self,
        tenant_id: uuid.UUID,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Machine], int]:
        filters = [Machine.tenant_id == tenant_id]
        if active_only:
            # Somente ativas: exclui soft-deleted e inativas
            filters.append(Machine.deleted_at.is_(None))
            filters.append(Machine.active.is_(True))
        # active_only=False → mostra TODAS, incluindo desativadas (deleted_at preenchido)
        return await self.list_paginated(*filters, page=page, page_size=page_size)

    async def search(
        self,
        tenant_id: uuid.UUID,
        q: str,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Machine], int]:
        """Busca por marca, modelo, nº de série ou placa (server-side, ILIKE)."""
        filters = [
            Machine.tenant_id == tenant_id,
            or_(
                Machine.brand.ilike(f"%{q}%"),
                Machine.model.ilike(f"%{q}%"),
                Machine.serial_number.ilike(f"%{q}%"),
                Machine.placa.ilike(f"%{q}%"),
            ),
        ]
        if active_only:
            filters.append(Machine.deleted_at.is_(None))
            filters.append(Machine.active.is_(True))
        return await self.list_paginated(*filters, page=page, page_size=page_size)

    async def list_by_client(
        self,
        client_id: uuid.UUID,
        tenant_id: uuid.UUID,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Machine], int]:
        filters = [
            Machine.client_id == client_id,
            Machine.tenant_id == tenant_id,
        ]
        if active_only:
            filters.append(Machine.deleted_at.is_(None))
            filters.append(Machine.active.is_(True))
        return await self.list_paginated(*filters, page=page, page_size=page_size)
