"""
Fixtures compartilhadas entre todos os testes.

Hierarquia de escopo:
  session → event_loop  (loop único compartilhado por fixtures E testes)
  session → engine      (cria/destrói tabelas 1x por run)
  function → db_session (BEGIN + rollback — isolamento por teste)
  function → http_client
  function → tenant, client_entity, machine, open_service_order, service_order_with_items

Decisões de arquitetura:
  - event_loop com scope="session" + asyncio.set_event_loop():
      pytest-asyncio 0.24 com asyncio_mode=auto cria loops function-scoped para
      os testes e loops separados para as fixtures quando asyncio_default_fixture_loop_scope
      é usado — o que faz conexões asyncpg criadas nas fixtures ficarem em um loop
      diferente do loop do teste → RuntimeError 'Future attached to different loop'.
      A solução é uma fixture event_loop customizada que chama set_event_loop(),
      forçando fixtures E testes a usarem o mesmo loop de sessão.
      Por isso asyncio_default_fixture_loop_scope NÃO deve estar no pytest.ini —
      tê-los simultaneamente cria dois loops de sessão concorrentes.
  - NullPool no engine: elimina conexões compartilhadas entre testes simultâneos.
  - autoflush=False na sessão de teste: evita MissingGreenlet ao manipular
    atributos ORM de forma síncrona (ex.: atribuição a coleções de relacionamento).
  - service_order_with_items usa add_all() + flush() + refresh() em vez de
    `order.items = [...]` para não disparar I/O síncrono dentro de greenlet.
  - Rollback no teardown envolto em try/except: se o código testado comitou a
    sessão (NfeProcessor._run nos E2E) ou asyncpg ficou em estado inválido,
    a exceção do rollback não mascara o erro original do teste.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import get_db_session
from app.main import app
from app.models.base import Base
from app.models.client import Client, DocumentType
from app.models.machine import Machine
from app.models.service_order import (
    ItemType,
    ServiceOrder,
    ServiceOrderItem,
    ServiceOrderStatus,
)
from app.models.tenant import Tenant
from app.models.user import User, UserRole

# ── URL do banco de teste ──────────────────────────────────────────────────────
# rsplit garante que apenas o nome do banco seja substituído,
# nunca o usuário/senha que também contém "automaster".
TEST_DB_URL = settings.DATABASE_URL.rsplit("/", 1)[0] + "/automaster_test"


# ── Event Loop único (scope=session) ─────────────────────────────────────────
# asyncio.set_event_loop() é obrigatório: garante que asyncpg crie conexões
# sempre no mesmo loop, independente de qual "Task" chama get_event_loop().
# Sem isso, fixtures e testes usam loops diferentes → asyncpg Future mismatch.

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)


# ── Engine (scope=session) ────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Cria as tabelas no banco de teste uma única vez por sessão de pytest."""
    eng = create_async_engine(TEST_DB_URL, poolclass=NullPool, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


# ── Session (scope=function, rollback após cada teste) ────────────────────────

@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """
    Cada teste roda dentro de uma transação que é revertida ao final.
    autoflush=False evita MissingGreenlet ao atribuir coleções ORM sem await.
    """
    # Garante que asyncio.get_event_loop() devolve o loop correto antes de
    # qualquer conexão asyncpg ser criada. pytest-asyncio pode limpar o loop
    # global entre testes; sem isso ocorre 'Future attached to a different loop'.
    asyncio.set_event_loop(asyncio.get_running_loop())

    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        await session.begin()
        try:
            yield session
        finally:
            # Rollback em try/except: se o código testado já comitou a sessão
            # (ex.: NfeProcessor._run nos E2E) ou se asyncpg ficou em estado
            # inválido, a exceção aqui não mascara o erro original do teste.
            try:
                await session.rollback()
            except Exception:
                pass


# ── HTTP Client com DB sobrescrita ────────────────────────────────────────────

@pytest_asyncio.fixture
async def http_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as client:
        yield client
    app.dependency_overrides.clear()


# ── Entidades base (factories inline) ─────────────────────────────────────────

@pytest_asyncio.fixture
async def tenant(db_session: AsyncSession) -> Tenant:
    t = Tenant(
        id=uuid.uuid4(),
        name="Oficina Teste",
        document="12345678000190",
        email="oficina@teste.com",
        razao_social="OFICINA TESTE LTDA",
        nome_fantasia="Oficina Teste",
        inscricao_estadual="123456789012",
        municipio="São Paulo",
        uf="SP",
        cep="01310100",
        codigo_municipio="3550308",
        logradouro="Rua das Flores",
        numero="123",
        bairro="Centro",
        crt="1",
        active=True,
    )
    db_session.add(t)
    await db_session.flush()
    return t


@pytest_asyncio.fixture
async def client_entity(db_session: AsyncSession, tenant: Tenant) -> Client:
    c = Client(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="João Silva",
        document="12345678901",
        document_type=DocumentType.CPF,
        email="joao@teste.com",
        phone="11999990000",
        municipio="São Paulo",
        uf="SP",
        cep="01310100",
        codigo_municipio="3550308",
        logradouro="Av. Paulista",
        numero="1000",
        bairro="Bela Vista",
        active=True,
    )
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def machine(db_session: AsyncSession, tenant: Tenant, client_entity: Client) -> Machine:
    m = Machine(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        client_id=client_entity.id,
        machine_type="Trator",
        model="7200",
        brand="John Deere",
        serial_number=f"JD-{uuid.uuid4().hex[:8].upper()}",
        year=2020,
        active=True,
    )
    db_session.add(m)
    await db_session.flush()
    return m


@pytest_asyncio.fixture
async def open_service_order(
    db_session: AsyncSession,
    tenant: Tenant,
    client_entity: Client,
    machine: Machine,
) -> ServiceOrder:
    so = ServiceOrder(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        client_id=client_entity.id,
        machine_id=machine.id,
        number=1,
        status=ServiceOrderStatus.ABERTA,
        description="Revisão geral e troca de óleo",
        opened_at=datetime.now(timezone.utc),
        total_services=Decimal("0.00"),
        total_parts=Decimal("0.00"),
        total_discount=Decimal("0.00"),
        total_amount=Decimal("0.00"),
    )
    db_session.add(so)
    await db_session.flush()
    return so


@pytest_asyncio.fixture
async def service_order_with_items(
    db_session: AsyncSession,
    open_service_order: ServiceOrder,
) -> ServiceOrder:
    """
    Persiste itens via FK sem atribuição direta a `open_service_order.items`.

    Por quê: `order.items = [...]` em SQLAlchemy assíncrono pode disparar
    um autoflush ou lazy-load síncrono → MissingGreenlet.
    Solução: add_all() + flush() + refresh(attribute_names=["items"]).
    """
    items = [
        ServiceOrderItem(
            id=uuid.uuid4(),
            service_order_id=open_service_order.id,
            item_type=ItemType.SERVICO,
            description="Revisão completa do motor",
            quantity=Decimal("1.000"),
            unit_price=Decimal("350.00"),
            discount=Decimal("0.00"),
            total_price=Decimal("350.00"),
        ),
        ServiceOrderItem(
            id=uuid.uuid4(),
            service_order_id=open_service_order.id,
            item_type=ItemType.PECA,
            description="Filtro de óleo",
            ncm_code="84212300",
            part_number="FO-4521",
            quantity=Decimal("2.000"),
            unit_price=Decimal("45.00"),
            discount=Decimal("0.00"),
            total_price=Decimal("90.00"),
        ),
    ]
    db_session.add_all(items)

    open_service_order.total_services = Decimal("350.00")
    open_service_order.total_parts = Decimal("90.00")
    open_service_order.total_amount = Decimal("440.00")

    await db_session.flush()

    # Recarrega a OS com os itens recém-persistidos; evita estado "stale"
    # e garante que order.items esteja populado para os testes.
    await db_session.refresh(open_service_order, attribute_names=["items"])

    return open_service_order


# ── Fixtures de autenticação ──────────────────────────────────────────────────

@pytest_asyncio.fixture
async def user_admin(db_session: AsyncSession, tenant: Tenant) -> User:
    """Usuário ADMIN para o tenant de teste — usado em testes de API."""
    from app.core.security import hash_password

    u = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="admin@teste.com",
        hashed_password=hash_password("senha123456"),
        full_name="Admin Teste",
        role=UserRole.ADMIN,
        active=True,
    )
    db_session.add(u)
    await db_session.flush()
    return u


# ── Header helpers ─────────────────────────────────────────────────────────────

def auth_headers(user: User) -> dict:
    """Gera o header Authorization: Bearer <token> para o usuário informado."""
    from app.core.security import create_access_token

    token = create_access_token(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        role=UserRole(user.role).value,
    )
    return {"Authorization": f"Bearer {token}"}


def tenant_headers(tenant: Tenant) -> dict:
    """Mantido para retrocompatibilidade — prefira auth_headers()."""
    return {"X-Tenant-ID": str(tenant.id)}
