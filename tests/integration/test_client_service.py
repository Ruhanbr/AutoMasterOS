"""
Testes de integração do ClientService.
Requerem PostgreSQL (automaster_test).
"""

import uuid

import pytest

from app.core.exceptions import DuplicateResourceException, ResourceNotFoundException
from app.models.client import DocumentType
from app.schemas.client import ClientCreate, ClientUpdate
from app.services.client_service import ClientService

pytestmark = pytest.mark.integration


class TestClientCreation:
    async def test_cria_cliente_cpf(self, db_session, tenant):
        data = ClientCreate(
            name="Maria Souza",
            document="98765432100",
            document_type=DocumentType.CPF,
            phone="11988880000",
            municipio="São Paulo",
            uf="SP",
        )
        client = await ClientService(db_session).create(tenant.id, data)
        assert client.id is not None
        assert client.name == "Maria Souza"
        assert client.document == "98765432100"
        assert client.tenant_id == tenant.id
        assert client.active is True

    async def test_cria_cliente_cnpj(self, db_session, tenant):
        data = ClientCreate(
            name="Fazenda São João LTDA",
            document="11222333000181",
            document_type=DocumentType.CNPJ,
        )
        client = await ClientService(db_session).create(tenant.id, data)
        assert client.document_type == DocumentType.CNPJ

    async def test_rejeita_documento_duplicado_no_mesmo_tenant(
        self, db_session, tenant, client_entity
    ):
        data = ClientCreate(
            name="Outro Nome",
            document=client_entity.document,
            document_type=DocumentType.CPF,
        )
        with pytest.raises(DuplicateResourceException):
            await ClientService(db_session).create(tenant.id, data)

    async def test_aceita_mesmo_documento_em_tenant_diferente(
        self, db_session, tenant, client_entity
    ):
        outro_tenant_id = uuid.uuid4()
        # Cria outro tenant primeiro
        from app.models.tenant import Tenant
        outro_tenant = Tenant(
            id=outro_tenant_id,
            name="Outra Oficina",
            document="99888777000166",
            email="outra@teste.com",
            razao_social="OUTRA OFICINA LTDA",
            crt="1",
            active=True,
        )
        db_session.add(outro_tenant)
        await db_session.flush()

        data = ClientCreate(
            name="Mesmo Documento",
            document=client_entity.document,
            document_type=DocumentType.CPF,
        )
        client2 = await ClientService(db_session).create(outro_tenant_id, data)
        assert client2.tenant_id == outro_tenant_id

    async def test_falha_com_tenant_inexistente(self, db_session):
        data = ClientCreate(
            name="X", document="12345678901", document_type=DocumentType.CPF
        )
        with pytest.raises(ResourceNotFoundException):
            await ClientService(db_session).create(uuid.uuid4(), data)


class TestClientRetrieval:
    async def test_busca_por_id(self, db_session, tenant, client_entity):
        found = await ClientService(db_session).get(tenant.id, client_entity.id)
        assert found.id == client_entity.id

    async def test_nao_encontrado_lanca_excecao(self, db_session, tenant):
        with pytest.raises(ResourceNotFoundException):
            await ClientService(db_session).get(tenant.id, uuid.uuid4())

    async def test_nao_cruza_tenants(self, db_session, client_entity):
        with pytest.raises(ResourceNotFoundException):
            await ClientService(db_session).get(uuid.uuid4(), client_entity.id)


class TestClientList:
    async def test_lista_por_tenant(self, db_session, tenant, client_entity):
        result = await ClientService(db_session).list(tenant.id)
        assert result.total >= 1
        ids = [c.id for c in result.items]
        assert client_entity.id in ids

    async def test_busca_por_nome_parcial(self, db_session, tenant, client_entity):
        result = await ClientService(db_session).list(
            tenant.id, name=client_entity.name[:4]
        )
        assert result.total >= 1

    async def test_paginacao(self, db_session, tenant, client_entity):
        result = await ClientService(db_session).list(tenant.id, page=1, page_size=5)
        assert result.page == 1
        assert result.page_size == 5


class TestClientUpdate:
    async def test_atualiza_telefone(self, db_session, tenant, client_entity):
        data = ClientUpdate(phone="11900001111")
        updated = await ClientService(db_session).update(tenant.id, client_entity.id, data)
        assert updated.phone == "11900001111"

    async def test_desativa_cliente(self, db_session, tenant, client_entity):
        result = await ClientService(db_session).deactivate(tenant.id, client_entity.id)
        assert result.active is False

    async def test_update_campos_nao_enviados_permanecem(
        self, db_session, tenant, client_entity
    ):
        original_name = client_entity.name
        data = ClientUpdate(phone="11900002222")
        updated = await ClientService(db_session).update(tenant.id, client_entity.id, data)
        assert updated.name == original_name
