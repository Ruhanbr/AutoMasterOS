"""
Script para criar o Administrador Master da plataforma AutoMaster.

Uso:
    docker compose exec backend python scripts/create_super_admin.py

O script cria (idempotente — pode rodar várias vezes sem duplicar):
  • Tenant "AutoMaster Platform" — tenant reservado para o SUPER_ADMIN
  • Usuário SUPER_ADMIN com as credenciais abaixo

Após rodar, acesse:
    http://localhost:3000/master/login
"""

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User, UserRole

# ── Configuração do administrador master ──────────────────────────────────────
PLATFORM_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
PLATFORM_DOCUMENT  = "00000000000000"

SUPER_ADMIN_EMAIL    = "automasterordemdeservico@gmail.com"
SUPER_ADMIN_PASSWORD = "AutoMaster2026"
SUPER_ADMIN_NAME     = "Administrador Master"
# ─────────────────────────────────────────────────────────────────────────────


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        async with session.begin():

            # 1. Cria platform tenant (se não existir)
            res = await session.execute(
                select(Tenant).where(Tenant.id == PLATFORM_TENANT_ID)
            )
            tenant = res.scalar_one_or_none()
            if tenant is None:
                tenant = Tenant(
                    id=PLATFORM_TENANT_ID,
                    name="AutoMaster Platform",
                    document=PLATFORM_DOCUMENT,
                    email="platform@automaster.com",
                    razao_social="AUTOMASTER PLATFORM LTDA",
                    crt="1",
                    active=True,
                    limite_tecnicos=0,
                )
                session.add(tenant)
                print("✅ Platform tenant criado.")
            else:
                print("ℹ️  Platform tenant já existe.")

            # 2. Cria SUPER_ADMIN (se não existir)
            res2 = await session.execute(
                select(User).where(
                    User.email == SUPER_ADMIN_EMAIL,
                    User.role == UserRole.SUPER_ADMIN,
                )
            )
            super_admin = res2.scalar_one_or_none()
            if super_admin is None:
                super_admin = User(
                    id=uuid.uuid4(),
                    tenant_id=PLATFORM_TENANT_ID,
                    email=SUPER_ADMIN_EMAIL,
                    hashed_password=hash_password(SUPER_ADMIN_PASSWORD),
                    full_name=SUPER_ADMIN_NAME,
                    role=UserRole.SUPER_ADMIN,
                    active=True,
                )
                session.add(super_admin)
                print(f"✅ SUPER_ADMIN criado: {SUPER_ADMIN_EMAIL}")
            else:
                # Atualiza senha se já existia
                super_admin.hashed_password = hash_password(SUPER_ADMIN_PASSWORD)
                print(f"ℹ️  SUPER_ADMIN já existe — senha redefinida.")

    await engine.dispose()

    print("\n" + "=" * 50)
    print("🔑  Credenciais do Administrador Master")
    print("=" * 50)
    print(f"   E-mail : {SUPER_ADMIN_EMAIL}")
    print(f"   Senha  : {SUPER_ADMIN_PASSWORD}")
    print(f"\n   Acesse : http://localhost:3000/master/login")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
