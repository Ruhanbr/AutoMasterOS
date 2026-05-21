"""
Testes unitários do model ServiceOrder.
Foco: máquina de estados e recalculate_totals().
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.service_order import (
    ItemType,
    ServiceOrder,
    ServiceOrderItem,
    ServiceOrderStatus,
)

pytestmark = pytest.mark.unit


class TestServiceOrderStatusMachine:
    """Garante que as transições de status são respeitadas."""

    def test_aberta_pode_ir_para_em_andamento(self):
        assert ServiceOrderStatus.ABERTA.can_transition_to(ServiceOrderStatus.EM_ANDAMENTO)

    def test_em_andamento_pode_ir_para_finalizada(self):
        assert ServiceOrderStatus.EM_ANDAMENTO.can_transition_to(ServiceOrderStatus.FINALIZADA)

    def test_aberta_nao_pode_ir_diretamente_para_finalizada(self):
        assert not ServiceOrderStatus.ABERTA.can_transition_to(ServiceOrderStatus.FINALIZADA)

    def test_finalizada_nao_tem_transicoes(self):
        assert not ServiceOrderStatus.FINALIZADA.can_transition_to(ServiceOrderStatus.ABERTA)
        assert not ServiceOrderStatus.FINALIZADA.can_transition_to(ServiceOrderStatus.EM_ANDAMENTO)

    def test_em_andamento_nao_pode_voltar_para_aberta(self):
        assert not ServiceOrderStatus.EM_ANDAMENTO.can_transition_to(ServiceOrderStatus.ABERTA)

    def test_allowed_transitions_retorna_dict_completo(self):
        transitions = ServiceOrderStatus.allowed_transitions()
        assert ServiceOrderStatus.ABERTA in transitions
        assert ServiceOrderStatus.EM_ANDAMENTO in transitions
        assert ServiceOrderStatus.FINALIZADA in transitions


class TestServiceOrderItemCompute:
    def test_compute_total_sem_desconto(self):
        item = ServiceOrderItem(
            quantity=Decimal("3.000"),
            unit_price=Decimal("50.00"),
            discount=Decimal("0.00"),
            total_price=Decimal("0.00"),
        )
        item.compute_total()
        assert item.total_price == Decimal("150.00")

    def test_compute_total_com_desconto(self):
        item = ServiceOrderItem(
            quantity=Decimal("2.000"),
            unit_price=Decimal("100.00"),
            discount=Decimal("30.00"),
            total_price=Decimal("0.00"),
        )
        item.compute_total()
        assert item.total_price == Decimal("170.00")


class TestServiceOrderRecalculateTotals:
    """
    Usa MagicMock para o ServiceOrder para evitar que o ORM do SQLAlchemy
    instrumente a coleção `items` e exija `_sa_instance_state` nos mocks.
    O método `recalculate_totals` é chamado diretamente via unbound call.
    """

    def _make_item(self, item_type: ItemType, total_price: Decimal) -> MagicMock:
        item = MagicMock(spec=ServiceOrderItem)
        item.item_type = item_type
        item.total_price = total_price
        return item

    def _make_order(self, discount: Decimal = Decimal("0.00")) -> MagicMock:
        order = MagicMock(spec=ServiceOrder)
        order.total_discount = discount
        return order

    def test_totais_separados_corretamente(self):
        order = self._make_order()
        order.items = [
            self._make_item(ItemType.SERVICO, Decimal("300.00")),
            self._make_item(ItemType.SERVICO, Decimal("150.00")),
            self._make_item(ItemType.PECA, Decimal("80.00")),
        ]
        ServiceOrder.recalculate_totals(order)
        assert order.total_services == Decimal("450.00")
        assert order.total_parts == Decimal("80.00")
        assert order.total_amount == Decimal("530.00")

    def test_desconto_subtraido_do_total(self):
        order = self._make_order(discount=Decimal("50.00"))
        order.items = [
            self._make_item(ItemType.SERVICO, Decimal("200.00")),
        ]
        ServiceOrder.recalculate_totals(order)
        assert order.total_amount == Decimal("150.00")

    def test_lista_vazia_resulta_em_zeros(self):
        order = self._make_order()
        order.items = []
        ServiceOrder.recalculate_totals(order)
        assert order.total_services == Decimal("0.00")
        assert order.total_parts == Decimal("0.00")
        assert order.total_amount == Decimal("0.00")
