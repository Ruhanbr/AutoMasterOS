"""
TecnicoLimitService — verifica se o tenant pode cadastrar mais técnicos.

Utiliza SELECT ... FOR UPDATE na linha do tenant para serializar acessos
concorrentes e evitar race conditions no contador de técnicos ativos.

Fluxo:
  1. Bloqueia a linha do tenant com FOR UPDATE.
  2. Conta técnicos ativos (role=TECNICO) no tenant.
  3. Levanta LimiteTecnicosExcedidoException se count >= limite_tecnicos.
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.user import User, UserRole


class LimiteTecnicosExcedidoException(Exception):
    """Levantada quando o tenant já atingiu o limite de técnicos ativos."""

    def __init__(self, atual: int, limite: int) -> None:
        self.atual = atual
        self.limite = limite
        super().__init__(
            f"Limite de técnicos atingido: {atual}/{limite} em uso."
        )


class TecnicoLimitService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enforce(self, tenant_id: uuid.UUID) -> None:
        """
        Verifica o limite de técnicos com lock de linha no tenant.

        O SELECT ... FOR UPDATE garante que duas requisições simultâneas
        não consigam passar pela verificação ao mesmo tempo — a segunda
        aguarda o COMMIT/ROLLBACK da primeira antes de prosseguir.

        Raises:
            LimiteTecnicosExcedidoException: quando count >= limite_tecnicos.
        """
        # 1. Lock da linha do tenant — serializa verificações concorrentes
        stmt_lock = (
            select(Tenant)
            .where(Tenant.id == tenant_id, Tenant.active.is_(True))
            .with_for_update()
        )
        result = await self._session.execute(stmt_lock)
        tenant = result.scalar_one_or_none()

        if tenant is None:
            # Tenant inexistente ou inativo — deixa o router decidir o 404
            return

        # 2. Conta técnicos ATIVOS no tenant
        stmt_count = (
            select(func.count())
            .select_from(User)
            .where(
                User.tenant_id == tenant_id,
                User.role == UserRole.TECNICO,
                User.active.is_(True),
            )
        )
        count_result = await self._session.execute(stmt_count)
        current_count: int = count_result.scalar_one()

        # 3. Rejeita se já atingiu o limite
        if current_count >= tenant.limite_tecnicos:
            raise LimiteTecnicosExcedidoException(
                atual=current_count,
                limite=tenant.limite_tecnicos,
            )
