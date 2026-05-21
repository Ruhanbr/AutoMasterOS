"""
Helpers de autorização multi-tenant.

Mapeamento do sistema real:
  - "OFICINA" = User com role=ADMIN (gestora da oficina dentro do tenant)
  - "TECNICO" = User com role=TECNICO
  - "MASTER"  = User com role=SUPER_ADMIN (vê tudo)
"""
import uuid
from typing import Optional

from fastapi import HTTPException, status

from app.models.user import User, UserRole


def require_admin_or_above(current_user: User) -> None:
    """Levanta 403 se usuário não for ADMIN ou SUPER_ADMIN."""
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores da oficina.",
        )


def get_os_tenant_filter(current_user: User) -> dict:
    """
    Retorna filtros de isolamento para queries de ServiceOrder.

    TECNICO  → filtra por technician_user_id (suas próprias OS)
    ADMIN    → filtra por tenant_id (todas as OS da oficina)
    SUPER_ADMIN → sem filtro adicional
    """
    if current_user.role == UserRole.TECNICO:
        return {"technician_user_id": current_user.id}
    elif current_user.role in (UserRole.ADMIN, UserRole.VIEWER):
        return {"tenant_id": current_user.tenant_id}
    # SUPER_ADMIN: sem filtro
    return {}


def get_client_tenant_filter(current_user: User) -> Optional[uuid.UUID]:
    """
    Retorna o tenant_id para filtrar queries de Client.
    SUPER_ADMIN retorna None (sem filtro).
    """
    if current_user.role == UserRole.SUPER_ADMIN:
        return None
    return current_user.tenant_id
