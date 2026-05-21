"""
Testes para a feature: Oficinas + Limite de Técnicos.

Cobre:
  - Cadastro de técnico dentro do limite → 201
  - Cadastro que excede o limite → 422
  - Atualização do limite_tecnicos via PATCH /tenants/{id}
  - Isolamento entre tenants (limite de um não afeta o outro)
  - Técnicos inativos não contam para o limite
  - Race condition: duas requisições simultâneas além do limite — apenas
    uma deve passar (a segunda leva 422 por causa do FOR UPDATE)
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import hash_password
from app.main import app
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from tests.conftest import auth_headers


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tecnico_payload(suffix: str = "") -> dict:
    return {
        "full_name": f"Técnico Teste{suffix}",
        "email": f"tecnico{suffix}@teste.com",
        "password": "senha12345678",
        "role": "TECNICO",
    }


def _admin_payload(suffix: str = "") -> dict:
    return {
        "full_name": f"Admin Teste{suffix}",
        "email": f"admin{suffix}@teste.com",
        "password": "senha12345678",
        "role": "ADMIN",
    }


async def _create_user_direct(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    role: UserRole,
    suffix: str = "",
    active: bool = True,
) -> User:
    """Cria usuário diretamente no banco (sem passar pelo limite)."""
    u = User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email=f"{role.value.lower()}{suffix}@direto.com",
        hashed_password=hash_password("senha12345678"),
        full_name=f"Direto {role.value}{suffix}",
        role=role,
        active=active,
    )
    session.add(u)
    await session.flush()
    return u


# ── Fixture: tenant com limite_tecnicos=2 ─────────────────────────────────────

@pytest_asyncio.fixture
async def tenant_limite2(db_session: AsyncSession) -> Tenant:
    t = Tenant(
        id=uuid.uuid4(),
        name="Oficina Limite",
        document="99887766000155",
        email="limite@oficina.com",
        razao_social="OFICINA LIMITE LTDA",
        nome_fantasia="Oficina Limite",
        crt="1",
        active=True,
        limite_tecnicos=2,
    )
    db_session.add(t)
    await db_session.flush()
    return t


@pytest_asyncio.fixture
async def admin_limite2(
    db_session: AsyncSession, tenant_limite2: Tenant
) -> User:
    return await _create_user_direct(
        db_session, tenant_limite2.id, UserRole.ADMIN, suffix="_admin"
    )


# ── Testes ─────────────────────────────────────────────────────────────────────

class TestLimiteTecnicos:
    """Suite de testes para o limite de técnicos por oficina."""

    # ── 1. Criação dentro do limite ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_criar_tecnico_dentro_do_limite(
        self,
        http_client: AsyncClient,
        tenant_limite2: Tenant,
        admin_limite2: User,
    ) -> None:
        """Deve criar técnico quando ainda há vagas."""
        headers = auth_headers(admin_limite2)
        r = await http_client.post("/api/v1/users", json=_tecnico_payload("_1"), headers=headers)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["role"] == "TECNICO"
        assert data["email"] == "tecnico_1@teste.com"

    # ── 2. Criação até o limite exato ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_criar_tecnicos_ate_limite_exato(
        self,
        http_client: AsyncClient,
        db_session: AsyncSession,
        tenant_limite2: Tenant,
        admin_limite2: User,
    ) -> None:
        """Deve criar exatamente limite_tecnicos técnicos."""
        headers = auth_headers(admin_limite2)

        for i in range(tenant_limite2.limite_tecnicos):
            r = await http_client.post(
                "/api/v1/users",
                json=_tecnico_payload(f"_lim{i}"),
                headers=headers,
            )
            assert r.status_code == 201, f"Técnico {i}: {r.text}"

    # ── 3. Criação acima do limite → 422 ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_rejeita_tecnico_alem_do_limite(
        self,
        http_client: AsyncClient,
        db_session: AsyncSession,
        tenant_limite2: Tenant,
        admin_limite2: User,
    ) -> None:
        """Deve retornar 422 ao tentar criar técnico além do limite."""
        headers = auth_headers(admin_limite2)

        # Preenche o limite via DB (sem passar pelo serviço)
        for i in range(tenant_limite2.limite_tecnicos):
            await _create_user_direct(
                db_session, tenant_limite2.id, UserRole.TECNICO, suffix=f"_fill{i}"
            )

        # Tentativa que excede o limite
        r = await http_client.post(
            "/api/v1/users",
            json=_tecnico_payload("_extra"),
            headers=headers,
        )
        assert r.status_code == 422, r.text
        detail = r.json()["detail"]
        assert "Limite de técnicos atingido" in detail

    # ── 4. Admin não conta para o limite ─────────────────────────────────────

    @pytest.mark.asyncio
    async def test_admin_nao_conta_para_limite(
        self,
        http_client: AsyncClient,
        db_session: AsyncSession,
        tenant_limite2: Tenant,
        admin_limite2: User,
    ) -> None:
        """Criar usuário com role ADMIN não deve ser bloqueado pelo limite de técnicos."""
        headers = auth_headers(admin_limite2)

        # Preenche todas as vagas de técnico
        for i in range(tenant_limite2.limite_tecnicos):
            await _create_user_direct(
                db_session, tenant_limite2.id, UserRole.TECNICO, suffix=f"_adm{i}"
            )

        # Criação de ADMIN deve passar mesmo com limite atingido
        r = await http_client.post(
            "/api/v1/users",
            json=_admin_payload("_novo"),
            headers=headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["role"] == "ADMIN"

    # ── 5. Técnicos inativos não contam ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_tecnicos_inativos_nao_contam(
        self,
        http_client: AsyncClient,
        db_session: AsyncSession,
        tenant_limite2: Tenant,
        admin_limite2: User,
    ) -> None:
        """Técnicos com active=False não devem contar para o limite."""
        headers = auth_headers(admin_limite2)

        # Cria técnicos inativos que preencheriam o limite
        for i in range(tenant_limite2.limite_tecnicos):
            await _create_user_direct(
                db_session,
                tenant_limite2.id,
                UserRole.TECNICO,
                suffix=f"_inativo{i}",
                active=False,
            )

        # Deve criar novo técnico (ativos = 0, inativos não contam)
        r = await http_client.post(
            "/api/v1/users",
            json=_tecnico_payload("_ativo"),
            headers=headers,
        )
        assert r.status_code == 201, r.text

    # ── 6. Isolamento entre tenants ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_limite_isolado_entre_tenants(
        self,
        http_client: AsyncClient,
        db_session: AsyncSession,
        tenant_limite2: Tenant,
        admin_limite2: User,
    ) -> None:
        """O limite de um tenant não deve interferir em outro tenant."""
        # Cria um segundo tenant com limite=1
        tenant_b = Tenant(
            id=uuid.uuid4(),
            name="Oficina B",
            document="11223344000166",
            email="b@oficina.com",
            razao_social="OFICINA B LTDA",
            crt="1",
            active=True,
            limite_tecnicos=1,
        )
        db_session.add(tenant_b)
        await db_session.flush()

        admin_b = await _create_user_direct(
            db_session, tenant_b.id, UserRole.ADMIN, suffix="_b"
        )

        # Preenche limite do tenant_b
        await _create_user_direct(
            db_session, tenant_b.id, UserRole.TECNICO, suffix="_bfull"
        )

        # tenant_limite2 (limite=2, 0 técnicos) ainda pode criar
        r = await http_client.post(
            "/api/v1/users",
            json=_tecnico_payload("_isolado"),
            headers=auth_headers(admin_limite2),
        )
        assert r.status_code == 201, f"Tenant A deveria poder criar: {r.text}"

        # tenant_b (limite=1, 1 técnico) já está cheio
        r_b = await http_client.post(
            "/api/v1/users",
            json=_tecnico_payload("_b_extra"),
            headers=auth_headers(admin_b),
        )
        assert r_b.status_code == 422, f"Tenant B deveria ser rejeitado: {r_b.text}"

    # ── 7. Atualização do limite via PATCH /tenants ───────────────────────────

    @pytest.mark.asyncio
    async def test_atualizar_limite_tecnicos(
        self,
        http_client: AsyncClient,
        tenant_limite2: Tenant,
    ) -> None:
        """PATCH /tenants/{id} deve aceitar e persistir novo limite_tecnicos."""
        r = await http_client.patch(
            f"/api/v1/tenants/{tenant_limite2.id}",
            json={"limite_tecnicos": 10},
        )
        assert r.status_code == 200, r.text
        assert r.json()["limite_tecnicos"] == 10

    # ── 8. Resposta inclui limite_tecnicos ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_tenant_inclui_limite(
        self,
        http_client: AsyncClient,
        tenant_limite2: Tenant,
    ) -> None:
        """GET /tenants/{id} deve retornar o campo limite_tecnicos."""
        r = await http_client.get(f"/api/v1/tenants/{tenant_limite2.id}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "limite_tecnicos" in data
        assert data["limite_tecnicos"] == tenant_limite2.limite_tecnicos

    # ── 9. GET /tenants lista todas oficinas ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_listar_tenants(
        self,
        http_client: AsyncClient,
        tenant_limite2: Tenant,
        tenant: Tenant,  # fixture da conftest
    ) -> None:
        """GET /tenants deve retornar lista de oficinas ativas."""
        r = await http_client.get("/api/v1/tenants/")
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list)
        ids = [item["id"] for item in items]
        assert str(tenant_limite2.id) in ids
        assert str(tenant.id) in ids

    # ── 10. Race condition — FOR UPDATE serializa acessos ────────────────────

    @pytest.mark.asyncio
    async def test_race_condition_limite(
        self,
        db_session: AsyncSession,
        tenant_limite2: Tenant,
    ) -> None:
        """
        Simula duas requisições simultâneas quando restam exatamente 1 vaga.

        Uma delas deve conseguir criar o técnico (201) e a outra deve ser
        rejeitada (422). O FOR UPDATE no TecnicoLimitService garante que a
        verificação e o insert sejam atômicos.

        Nota: este teste usa sessões independentes (não a db_session do fixture)
        para simular o comportamento real de duas conexões concorrentes.
        """
        from sqlalchemy.ext.asyncio import (
            AsyncSession as _AS,
            async_sessionmaker,
            create_async_engine,
        )
        from sqlalchemy.pool import NullPool
        from app.core.config import settings

        TEST_DB_URL = settings.DATABASE_URL.rsplit("/", 1)[0] + "/automaster_test"

        engine = create_async_engine(TEST_DB_URL, poolclass=NullPool, echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False)

        # Cria o tenant e admin com limite=1 em sessão separada
        async with factory() as setup_session:
            t = Tenant(
                id=uuid.uuid4(),
                name="Oficina Race",
                document="55566677000188",
                email="race@oficina.com",
                razao_social="RACE LTDA",
                crt="1",
                active=True,
                limite_tecnicos=1,
            )
            setup_session.add(t)
            admin = User(
                id=uuid.uuid4(),
                tenant_id=t.id,
                email="race_admin@teste.com",
                hashed_password=hash_password("senha12345678"),
                full_name="Race Admin",
                role=UserRole.ADMIN,
                active=True,
            )
            setup_session.add(admin)
            await setup_session.commit()

        tenant_id = t.id

        from app.services.tecnico_limit_service import (
            LimiteTecnicosExcedidoException,
            TecnicoLimitService,
        )

        results: list[str] = []

        async def try_create(tag: str) -> None:
            async with factory() as sess:
                async with sess.begin():
                    try:
                        await TecnicoLimitService(sess).enforce(tenant_id)
                        # Cria o técnico se passou pelo enforce
                        u = User(
                            id=uuid.uuid4(),
                            tenant_id=tenant_id,
                            email=f"race_tec_{tag}@teste.com",
                            hashed_password=hash_password("senha12345678"),
                            full_name=f"Race Tec {tag}",
                            role=UserRole.TECNICO,
                            active=True,
                        )
                        sess.add(u)
                        await sess.flush()
                        results.append("ok")
                    except LimiteTecnicosExcedidoException:
                        results.append("rejected")

        # Dispara as duas corrotinas "simultaneamente"
        await asyncio.gather(try_create("A"), try_create("B"))

        ok_count = results.count("ok")
        rejected_count = results.count("rejected")

        # Com FOR UPDATE apenas 1 deve criar e 1 deve ser rejeitado
        assert ok_count == 1, f"Esperado 1 criação, obtido {ok_count}. results={results}"
        assert rejected_count == 1, f"Esperado 1 rejeição, obtido {rejected_count}. results={results}"

        # Cleanup
        await engine.dispose()
