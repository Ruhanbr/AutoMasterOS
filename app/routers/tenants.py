import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.core.dependencies import DbSession, require_super_admin
from app.core.exceptions import AutoMasterException, to_http_exception
from app.core.security import hash_password
from app.core.logging import get_logger
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.tenant import (
    TenantCreate,
    TenantResponse,
    TenantSetupPayload,
    TenantSetupResponse,
    TenantUpdate,
)
from app.services.password_service import PasswordService
from app.services.email_service import send_temp_password
from app.services.tenant_service import TenantService

logger = get_logger(__name__)

router = APIRouter(prefix="/tenants", tags=["tenants"])

_super_admin = [Depends(require_super_admin)]

LOGO_DIR = Path("/app/static/logos")

# Document do platform tenant (reservado — nunca aparece na lista)
_PLATFORM_DOCUMENT = "00000000000000"


@router.get("/", response_model=List[TenantResponse])
async def list_tenants(session: DbSession):
    """Lista todas as oficinas (tenants) ativas da plataforma."""
    stmt = (
        select(Tenant)
        .where(Tenant.active.is_(True), Tenant.document != _PLATFORM_DOCUMENT)
        .order_by(Tenant.name)
    )
    result = await session.execute(stmt)
    tenants = result.scalars().all()
    return [TenantResponse.model_validate(t) for t in tenants]


@router.post(
    "/setup",
    response_model=TenantSetupResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=_super_admin,
    summary="Cria oficina + admin em uma única operação",
)
async def setup_tenant(data: TenantSetupPayload, session: DbSession):
    """
    Cria a oficina e o primeiro usuário ADMIN dela.
    Envia a senha temporária por email automaticamente.
    Requer SUPER_ADMIN.
    """
    # 1. Cria o tenant (reutiliza TenantService para validação de CNPJ duplicado)
    tenant_create = TenantCreate(
        name=data.name,
        document=data.document,
        email=data.email,
        phone=data.phone,
        razao_social=data.razao_social,
        nome_fantasia=data.nome_fantasia,
        municipio=data.municipio,
        uf=data.uf,
        cep=data.cep,
        logradouro=data.logradouro,
        numero=data.numero,
        bairro=data.bairro,
        inscricao_estadual=data.inscricao_estadual,
        limite_tecnicos=data.limite_tecnicos,
        regime_tributario=data.regime_tributario,
        crt=data.crt,
    )
    try:
        tenant = await TenantService(session).create(tenant_create)
    except AutoMasterException as exc:
        raise to_http_exception(exc)

    # 2. Verifica se já existe user ativo em uma oficina ATIVA com esse email
    from sqlalchemy import select as sa_select
    conflict = await session.execute(
        sa_select(User)
        .join(Tenant, User.tenant_id == Tenant.id)
        .where(
            User.email == data.admin_email,
            User.active.is_(True),
            Tenant.active.is_(True),
        )
    )
    if conflict.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe um usuário ativo com o e-mail '{data.admin_email}' em uma oficina ativa.",
        )

    # 3. Gera senha temporária e cria o ADMIN da oficina
    senha_temp = PasswordService.gerar_senha_temporaria()
    admin_user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=data.admin_email,
        hashed_password=hash_password(senha_temp),
        full_name=data.admin_nome,
        role=UserRole.ADMIN,
        active=True,
        precisa_trocar_senha=True,
    )
    session.add(admin_user)
    await session.flush()
    await session.commit()

    # 4. Envia email com credenciais
    try:
        await send_temp_password(admin_user.email, admin_user.full_name, senha_temp, tenant_id=str(tenant.id))
        logger.info(
            "setup_tenant_email_enviado",
            tenant_id=str(tenant.id),
            admin_email=admin_user.email,
        )
    except Exception as e:
        logger.warning("setup_tenant_email_falhou", error=str(e), tenant_id=str(tenant.id))

    return TenantSetupResponse(
        tenant=TenantResponse.model_validate(tenant),
        admin_email=admin_user.email,
        message=(
            f"Oficina criada com sucesso! "
            f"As credenciais de acesso foram enviadas para {admin_user.email}."
        ),
    )


@router.post(
    "/",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=_super_admin,
)
async def create_tenant(data: TenantCreate, session: DbSession):
    """Cria uma nova oficina (sem usuário). Requer SUPER_ADMIN."""
    try:
        tenant = await TenantService(session).create(data)
        return TenantResponse.model_validate(tenant)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: uuid.UUID, session: DbSession):
    try:
        tenant = await TenantService(session).get(tenant_id)
        return TenantResponse.model_validate(tenant)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.patch(
    "/{tenant_id}",
    response_model=TenantResponse,
    dependencies=_super_admin,
)
async def update_tenant(tenant_id: uuid.UUID, data: TenantUpdate, session: DbSession):
    """Atualiza dados de uma oficina. Requer SUPER_ADMIN."""
    try:
        tenant = await TenantService(session).update(tenant_id, data)
        return TenantResponse.model_validate(tenant)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.delete(
    "/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_super_admin,
    summary="Desativa (exclui) uma oficina",
)
async def delete_tenant(tenant_id: uuid.UUID, session: DbSession):
    """
    Soft-delete: marca a oficina como inativa.
    Dados históricos são preservados. Requer SUPER_ADMIN.
    """
    try:
        await TenantService(session).delete(tenant_id)
        await session.commit()
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.post(
    "/{tenant_id}/logo",
    response_model=TenantResponse,
    dependencies=_super_admin,
    summary="Upload de logo da oficina",
)
async def upload_tenant_logo(
    tenant_id: uuid.UUID,
    session: DbSession,
    file: UploadFile = File(...),
) -> TenantResponse:
    """
    Faz upload do logotipo da oficina (PNG/JPG/WebP, máx 3 MB).
    A imagem é salva em /app/static/logos/ e o caminho é armazenado no tenant.
    Requer SUPER_ADMIN.
    """
    allowed_types = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Formato inválido. Use PNG, JPEG ou WebP.")

    contents = await file.read()
    if len(contents) > 3 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Arquivo muito grande (máx 3 MB).")

    try:
        tenant = await TenantService(session).get(tenant_id)
    except AutoMasterException as exc:
        raise to_http_exception(exc)

    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    ext = "png" if "png" in (file.content_type or "") else ("webp" if "webp" in (file.content_type or "") else "jpg")
    logo_path = LOGO_DIR / f"{tenant_id}.{ext}"
    logo_path.write_bytes(contents)

    tenant.logo_url = str(logo_path)
    await session.flush()
    await session.commit()
    await session.refresh(tenant)

    return TenantResponse.model_validate(tenant)


@router.delete(
    "/{tenant_id}/logo",
    response_model=TenantResponse,
    dependencies=_super_admin,
    summary="Remove o logo da oficina",
)
async def remove_tenant_logo(tenant_id: uuid.UUID, session: DbSession) -> TenantResponse:
    """Remove o logotipo da oficina. Requer SUPER_ADMIN."""
    try:
        tenant = await TenantService(session).get(tenant_id)
    except AutoMasterException as exc:
        raise to_http_exception(exc)

    if tenant.logo_url:
        try:
            Path(tenant.logo_url).unlink(missing_ok=True)
        except Exception:
            pass
        tenant.logo_url = None
        await session.flush()
        await session.commit()
        await session.refresh(tenant)

    return TenantResponse.model_validate(tenant)
