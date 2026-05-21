"""
Testes unitários do calculador tributário.
Não requerem banco de dados.
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.service_order import ItemType, ServiceOrder, ServiceOrderItem
from app.utils.tax_calculator import TaxCalculationResult, TaxCalculator, _round2

pytestmark = pytest.mark.unit


def make_item(
    item_type: ItemType,
    description: str,
    quantity: Decimal,
    unit_price: Decimal,
    discount: Decimal = Decimal("0.00"),
    ncm_code: str | None = None,
) -> ServiceOrderItem:
    item = MagicMock(spec=ServiceOrderItem)
    item.id = uuid.uuid4()
    item.item_type = item_type
    item.description = description
    item.quantity = quantity
    item.unit_price = unit_price
    item.discount = discount
    item.total_price = (quantity * unit_price) - discount
    item.ncm_code = ncm_code
    return item


def make_order(items: list) -> ServiceOrder:
    order = MagicMock(spec=ServiceOrder)
    order.items = items
    return order


class TestTaxCalculator:
    def setup_method(self):
        self.calc = TaxCalculator()

    def test_servico_usa_cfop_5933(self):
        items = [make_item(ItemType.SERVICO, "Revisão", Decimal("1"), Decimal("200.00"))]
        result = self.calc.calculate(make_order(items))
        assert result.items[0].cfop == "5933"

    def test_peca_usa_cfop_5949(self):
        items = [make_item(ItemType.PECA, "Filtro", Decimal("1"), Decimal("50.00"))]
        result = self.calc.calculate(make_order(items))
        assert result.items[0].cfop == "5949"

    def test_servico_csosn_400(self):
        items = [make_item(ItemType.SERVICO, "Revisão", Decimal("1"), Decimal("100.00"))]
        result = self.calc.calculate(make_order(items))
        assert result.items[0].csosn == "400"

    def test_peca_csosn_102(self):
        items = [make_item(ItemType.PECA, "Peca", Decimal("1"), Decimal("100.00"))]
        result = self.calc.calculate(make_order(items))
        assert result.items[0].csosn == "102"

    def test_icms_zero_simples_nacional(self):
        items = [make_item(ItemType.PECA, "Peca", Decimal("2"), Decimal("50.00"))]
        result = self.calc.calculate(make_order(items))
        assert result.items[0].valor_icms == Decimal("0.00")
        assert result.items[0].base_icms == Decimal("0.00")

    def test_pis_cofins_cst_07(self):
        items = [make_item(ItemType.SERVICO, "Svc", Decimal("1"), Decimal("300.00"))]
        result = self.calc.calculate(make_order(items))
        assert result.items[0].cst_pis == "07"
        assert result.items[0].cst_cofins == "07"
        assert result.items[0].valor_pis == Decimal("0.00")
        assert result.items[0].valor_cofins == Decimal("0.00")

    def test_total_tributos_ibpt_9_5_porcento(self):
        items = [make_item(ItemType.SERVICO, "Svc", Decimal("1"), Decimal("1000.00"))]
        result = self.calc.calculate(make_order(items))
        expected = _round2(Decimal("1000.00") * Decimal("0.0950"))
        assert result.items[0].valor_total_tributos == expected

    def test_totais_separados_servicos_pecas(self):
        items = [
            make_item(ItemType.SERVICO, "Revisão", Decimal("1"), Decimal("200.00")),
            make_item(ItemType.PECA, "Filtro", Decimal("2"), Decimal("30.00")),
        ]
        result = self.calc.calculate(make_order(items))
        assert result.valor_servicos == Decimal("200.00")
        assert result.valor_produtos == Decimal("60.00")
        assert result.valor_total_nf == Decimal("260.00")

    def test_multiplos_itens_soma_correta(self):
        items = [
            make_item(ItemType.SERVICO, "S1", Decimal("1"), Decimal("100.00")),
            make_item(ItemType.SERVICO, "S2", Decimal("3"), Decimal("50.00")),
            make_item(ItemType.PECA, "P1", Decimal("5"), Decimal("20.00")),
        ]
        result = self.calc.calculate(make_order(items))
        assert result.valor_total_nf == Decimal("350.00")  # 100 + 150 + 100

    def test_resultado_tem_regime_simples_nacional(self):
        items = [make_item(ItemType.SERVICO, "S", Decimal("1"), Decimal("100.00"))]
        result = self.calc.calculate(make_order(items))
        assert result.regime == "Simples Nacional"

    def test_to_dict_serializa_decimais_como_string(self):
        items = [make_item(ItemType.SERVICO, "S", Decimal("1"), Decimal("100.00"))]
        result = self.calc.calculate(make_order(items))
        d = result.to_dict()
        assert isinstance(d["valor_total_nf"], str)
        assert isinstance(d["valor_icms_total"], str)

    def test_ncm_servico_default_quando_ausente(self):
        items = [make_item(ItemType.SERVICO, "Serviço sem NCM", Decimal("1"), Decimal("100.00"))]
        result = self.calc.calculate(make_order(items))
        assert result.items[0].ncm == "00000000"

    def test_ncm_informado_prevalece(self):
        items = [make_item(ItemType.PECA, "Peca", Decimal("1"), Decimal("50.00"), ncm_code="84212300")]
        result = self.calc.calculate(make_order(items))
        assert result.items[0].ncm == "84212300"
