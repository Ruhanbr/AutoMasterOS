"""
Testes de integração do MachineService.
"""

import uuid

import pytest

from app.core.exceptions import DuplicateResourceException, ResourceNotFoundException
from app.schemas.machine import MachineCreate, MachineUpdate
from app.services.machine_service import MachineService

pytestmark = pytest.mark.integration


class TestMachineCreation:
    async def test_cria_maquina(self, db_session, tenant, client_entity):
        data = MachineCreate(
            client_id=client_entity.id,
            machine_type="Colheitadeiras",
            model="S680",
            brand="John Deere",
            serial_number=f"JD-{uuid.uuid4().hex[:8].upper()}",
            year=2022,
        )
        machine = await MachineService(db_session).create(tenant.id, data)
        assert machine.id is not None
        assert machine.tenant_id == tenant.id
        assert machine.client_id == client_entity.id
        assert machine.active is True

    async def test_rejeita_serial_duplicado(self, db_session, tenant, client_entity, machine):
        data = MachineCreate(
            client_id=client_entity.id,
            machine_type="Tratores",
            model="8250",
            brand="John Deere",
            serial_number=machine.serial_number,
        )
        with pytest.raises(DuplicateResourceException):
            await MachineService(db_session).create(tenant.id, data)

    async def test_rejeita_cliente_de_outro_tenant(self, db_session, client_entity):
        data = MachineCreate(
            client_id=client_entity.id,
            machine_type="Tratores",
            model="X",
            brand="Y",
            serial_number="SN-OUTRO-TENANT-001",
        )
        with pytest.raises(ResourceNotFoundException):
            await MachineService(db_session).create(uuid.uuid4(), data)

    async def test_rejeita_cliente_inexistente(self, db_session, tenant):
        data = MachineCreate(
            client_id=uuid.uuid4(),
            machine_type="Tratores",
            model="X",
            brand="Y",
            serial_number="SN-CLIENTE-INEXISTENTE",
        )
        with pytest.raises(ResourceNotFoundException):
            await MachineService(db_session).create(tenant.id, data)


class TestMachineRetrieval:
    async def test_busca_por_id(self, db_session, tenant, machine):
        found = await MachineService(db_session).get(tenant.id, machine.id)
        assert found.id == machine.id

    async def test_nao_encontrado_lanca_excecao(self, db_session, tenant):
        with pytest.raises(ResourceNotFoundException):
            await MachineService(db_session).get(tenant.id, uuid.uuid4())

    async def test_nao_cruza_tenants(self, db_session, machine):
        with pytest.raises(ResourceNotFoundException):
            await MachineService(db_session).get(uuid.uuid4(), machine.id)


class TestMachineList:
    async def test_lista_por_tenant(self, db_session, tenant, machine):
        result = await MachineService(db_session).list(tenant.id)
        assert result.total >= 1

    async def test_filtra_por_cliente(self, db_session, tenant, client_entity, machine):
        result = await MachineService(db_session).list(
            tenant.id, client_id=client_entity.id
        )
        assert result.total >= 1
        for m in result.items:
            assert m.client_id == client_entity.id


class TestMachineUpdate:
    async def test_atualiza_notas(self, db_session, tenant, machine):
        data = MachineUpdate(notes="Motor revisado em 2024")
        updated = await MachineService(db_session).update(tenant.id, machine.id, data)
        assert updated.notes == "Motor revisado em 2024"

    async def test_desativa_maquina(self, db_session, tenant, machine):
        result = await MachineService(db_session).deactivate(tenant.id, machine.id)
        assert result.active is False
