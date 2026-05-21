"""
Dependências FastAPI reutilizáveis.

get_current_user  — valida Bearer JWT e retorna o User autenticado
get_tenant_id     — extrai tenant_id do JWT (via get_current_user)
require_role      — guard de RBAC: exige uma das roles informadas
DbSession         — sessão assíncrona do banco (injetada por request)
CurrentUser       — atalho tipado para Depends(get_current_user)
TenantId          — atalho tipado para Depends(get_tenant_id)
"""

import uuid
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import decode_token
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository

_bearer = HTTPBearer(auto_error=False)


# ── Autenticação ──────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """Valida o Bearer token e retorna o User correspondente."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Token de autenticação não informado",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise JWTError("not an access token")
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise JWTError("missing sub")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Token inválido ou expirado"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await UserRepository(session).get_by_id(uuid.UUID(user_id))
    if user is None or not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Usuário não encontrado ou inativo"},
        )
    return user


async def get_tenant_id(
    current_user: User = Depends(get_current_user),
) -> uuid.UUID:
    """Extrai o tenant_id do usuário autenticado via JWT."""
    return current_user.tenant_id


# ── RBAC ──────────────────────────────────────────────────────────────────────

def require_role(*roles: UserRole):
    """
    Dependência de role-based access control.

    Uso:
        @router.delete("/...", dependencies=[Depends(require_role(UserRole.ADMIN))])
    """
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": "Permissão insuficiente para esta operação",
                },
            )
        return current_user

    return checker


# ── Client Ownership (X-Cliente-ID) ───────────────────────────────────────────

async def get_cliente_id(
    x_cliente_id: Optional[str] = Header(None, alias="X-Cliente-ID"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> uuid.UUID | None:
    """
    Extrai e valida o header opcional X-Cliente-ID.

    • Ausente  → retorna None  (modo admin — comportamento existente mantido)
    • Presente → valida UUID + pertence ao tenant → retorna uuid.UUID
    • Inválido / não pertence ao tenant → 400 / 403

    Esse header é a chave de isolamento cliente a cliente:
    qualquer query de máquina com esse valor só verá máquinas
    cujo client_id == X-Cliente-ID.
    """
    if x_cliente_id is None:
        return None

    try:
        client_id = uuid.UUID(x_cliente_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_HEADER",
                "message": "X-Cliente-ID deve ser um UUID válido",
            },
        )

    from app.repositories.client_repository import ClientRepository

    client = await ClientRepository(session).get_by_id_and_tenant(
        client_id, current_user.tenant_id
    )
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "CLIENT_OWNERSHIP_VIOLATION",
                "message": "Cliente não encontrado neste tenant",
            },
        )
    return client_id


async def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Acesso restrito ao administrador master"},
        )
    return current_user


# ── Atalhos tipados ───────────────────────────────────────────────────────────

TenantId   = Annotated[uuid.UUID,        Depends(get_tenant_id)]
DbSession  = Annotated[AsyncSession,     Depends(get_db_session)]
CurrentUser = Annotated[User,            Depends(get_current_user)]
ClientId   = Annotated[uuid.UUID | None, Depends(get_cliente_id)]
