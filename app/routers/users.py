"""
Gerenciamento de usuários/técnicos do tenant.
"""
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, EmailStr, Field

from app.core.authorization import require_admin_or_above
from app.core.dependencies import CurrentUser, DbSession, TenantId
from app.core.exceptions import AutoMasterException, to_http_exception
from app.core.logging import get_logger
from app.core.security import hash_password

logger = get_logger(__name__)
from app.models.user import UserRole
from app.repositories.tenant_repository import TenantRepository
from sqlalchemy import select as _sa_select, func as _func
from app.repositories.user_repository import UserRepository
from app.schemas.auth import UserResponse
from app.services.tecnico_limit_service import (
    LimiteTecnicosExcedidoException,
    TecnicoLimitService,
)

router = APIRouter(prefix="/users", tags=["users"])

SIGNATURE_DIR = Path("/app/static/signatures")


async def _count_active_admins(session, tenant_id: uuid.UUID, exclude_user_id: uuid.UUID | None = None) -> int:
    """Retorna quantos ADMINs ativos o tenant possui, opcionalmente excluindo um usuário."""
    from app.models.user import User
    q = _sa_select(_func.count(User.id)).where(
        User.tenant_id == tenant_id,
        User.role == UserRole.ADMIN,
        User.active.is_(True),
    )
    if exclude_user_id:
        q = q.where(User.id != exclude_user_id)
    result = await session.execute(q)
    return result.scalar() or 0


# ── Schemas ────────────────────────────────────────────────────────────────────

class UserCreatePayload(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8)
    role: UserRole = UserRole.TECNICO


class UserUpdatePayload(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=200)
    email: EmailStr | None = None
    role: UserRole | None = None
    active: bool | None = None


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=UserListResponse)
async def list_users(
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    role: Optional[UserRole] = Query(None),
    active_only: bool = Query(True),
) -> UserListResponse:
    """Lista todos os usuários/técnicos do tenant."""
    repo = UserRepository(session)
    users = await repo.list_by_tenant(tenant_id, role=role, active_only=active_only)
    return UserListResponse(items=users, total=len(users))


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreatePayload,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
) -> UserResponse:
    """Cria um novo usuário/técnico no tenant. Requer ADMIN ou SUPER_ADMIN."""
    require_admin_or_above(current_user)  # 🔒 TECNICO não pode criar usuários
    repo = UserRepository(session)

    # Verifica limite de técnicos (antes do e-mail, para falhar mais cedo)
    if payload.role == UserRole.TECNICO:
        try:
            await TecnicoLimitService(session).enforce(tenant_id)
        except LimiteTecnicosExcedidoException as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Limite de técnicos atingido: {exc.atual}/{exc.limite} em uso. "
                       "Solicite ao administrador da plataforma o aumento do limite.",
            )

    # Verifica duplicidade de email no tenant
    existing = await repo.get_by_email_and_tenant(payload.email, tenant_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um usuário com este e-mail nesta oficina.",
        )

    user = await repo.create(
        tenant_id=tenant_id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        active=True,
        precisa_trocar_senha=False,
    )
    await session.commit()

    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdatePayload,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
) -> UserResponse:
    """Atualiza dados de um usuário/técnico."""
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)

    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.email is not None:
        # Verifica conflito de email (outro usuário com mesmo email no tenant)
        conflict = await repo.get_by_email_and_tenant(payload.email, tenant_id)
        if conflict and conflict.id != user_id:
            raise HTTPException(status_code=409, detail="E-mail já em uso por outro usuário.")
        user.email = payload.email
    if payload.role is not None:
        # Impede rebaixar o último ADMIN ativo do tenant
        if user.role == UserRole.ADMIN and payload.role != UserRole.ADMIN:
            remaining = await _count_active_admins(session, tenant_id, exclude_user_id=user_id)
            if remaining == 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Não é possível alterar o papel deste usuário: ele é o único administrador ativo da oficina.",
                )
        user.role = payload.role

    if payload.active is not None and payload.active is False:
        # Impede desativar o último ADMIN ativo do tenant
        if user.role == UserRole.ADMIN:
            remaining = await _count_active_admins(session, tenant_id, exclude_user_id=user_id)
            if remaining == 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Não é possível desativar este usuário: ele é o único administrador ativo da oficina.",
                )
        user.active = payload.active
    elif payload.active is True:
        user.active = True

    user = await repo.save(user)
    await session.commit()
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
) -> None:
    """
    Desativa (soft-delete) um usuário/técnico do tenant.
    - Requer ADMIN ou SUPER_ADMIN.
    - Bloqueado se o técnico tiver OS abertas ou em andamento.
    """
    require_admin_or_above(current_user)

    from sqlalchemy import select as sa_select
    from app.models.service_order import ServiceOrder, ServiceOrderStatus

    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)

    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    # Impede desativar a si mesmo
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Você não pode desativar a sua própria conta.",
        )

    # Impede desativar o último ADMIN ativo do tenant
    if user.role == UserRole.ADMIN:
        remaining = await _count_active_admins(session, tenant_id, exclude_user_id=user_id)
        if remaining == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Não é possível desativar este usuário: ele é o único administrador ativo da oficina.",
            )

    # Verifica OS abertas ou em andamento vinculadas ao usuário
    os_ativas = await session.execute(
        sa_select(ServiceOrder).where(
            ServiceOrder.technician_user_id == user_id,
            ServiceOrder.tenant_id == tenant_id,
            ServiceOrder.status.in_([
                ServiceOrderStatus.ABERTA,
                ServiceOrderStatus.EM_ANDAMENTO,
            ]),
        ).limit(1)
    )
    if os_ativas.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Não é possível desativar este técnico: ele possui ordens de serviço "
                "abertas ou em andamento. Finalize ou reatribua as OS antes de continuar."
            ),
        )

    user.active = False
    await repo.save(user)
    await session.commit()
    logger.info("usuario_desativado", user_id=str(user_id), by=str(current_user.id))


@router.post("/{user_id}/signature", response_model=UserResponse)
async def upload_signature(
    user_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> UserResponse:
    """
    Faz upload da assinatura do técnico (PNG/JPG, máx 2 MB).
    A imagem é salva em /app/static/signatures/ e o caminho é armazenado no usuário.
    """
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)

    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    # Valida tipo e tamanho
    allowed_types = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Formato inválido. Use PNG ou JPEG.",
        )

    contents = await file.read()
    if len(contents) > 2 * 1024 * 1024:  # 2 MB
        raise HTTPException(status_code=400, detail="Arquivo muito grande (máx 2 MB).")

    # Garante que o diretório existe
    SIGNATURE_DIR.mkdir(parents=True, exist_ok=True)

    ext = "png" if "png" in (file.content_type or "") else "jpg"
    sig_path = SIGNATURE_DIR / f"{user_id}.{ext}"
    sig_path.write_bytes(contents)

    user.assinatura_url = str(sig_path)
    user = await repo.save(user)
    await session.commit()

    return UserResponse.model_validate(user)


@router.delete("/{user_id}/signature", response_model=UserResponse)
async def remove_signature(
    user_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
) -> UserResponse:
    """Remove a assinatura do técnico."""
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)

    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if user.assinatura_url:
        try:
            Path(user.assinatura_url).unlink(missing_ok=True)
        except Exception:
            pass
        user.assinatura_url = None
        user = await repo.save(user)
        await session.commit()

    return UserResponse.model_validate(user)
