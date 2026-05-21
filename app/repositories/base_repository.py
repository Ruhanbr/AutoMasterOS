import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """
    Repository genérico com operações CRUD assíncronas.
    Cada repositório concreto herda e especializa conforme o modelo.
    """

    def __init__(self, model: type[ModelT], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> ModelT | None:
        result = await self.session.get(self.model, id)
        return result

    async def get_by_id_or_raise(
        self, id: uuid.UUID, error_class: type[Exception] | None = None
    ) -> ModelT:
        instance = await self.get_by_id(id)
        if instance is None:
            if error_class:
                raise error_class(self.model.__name__, str(id))
            raise ValueError(f"{self.model.__name__} id={id} não encontrado")
        return instance

    async def create(self, **kwargs: Any) -> ModelT:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def save(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)
        await self.session.flush()

    async def count(self, *filters: Any) -> int:
        stmt = select(func.count()).select_from(self.model)
        if filters:
            stmt = stmt.where(*filters)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists(self, *filters: Any) -> bool:
        return await self.count(*filters) > 0

    async def list_paginated(
        self,
        *filters: Any,
        page: int = 1,
        page_size: int = 20,
        order_by: Any = None,
    ) -> tuple[list[ModelT], int]:
        offset = (page - 1) * page_size

        count_stmt = select(func.count()).select_from(self.model)
        if filters:
            count_stmt = count_stmt.where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(self.model)
        if filters:
            stmt = stmt.where(*filters)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        else:
            stmt = stmt.order_by(self.model.created_at.desc())  # type: ignore[attr-defined]
        stmt = stmt.offset(offset).limit(page_size)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total
