"""
Calculadora tributária para Simples Nacional (CRT 1).

Tabelas de referência:
  CSOSN 400  — Não tributado no Simples Nacional (saída interna de serviços)
  CSOSN 102  — Tributado sem permissão de crédito (mercadorias)
  PIS/COFINS CST 07 — Operação isenta no Simples Nacional
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.models.service_order import ItemType, ServiceOrder, ServiceOrderItem


@dataclass
class ItemTax:
    item_id: str
    description: str
    item_type: ItemType
    quantity: Decimal
    unit_price: Decimal
    total_price: Decimal
    cfop: str
    ncm: str
    csosn: str
    cst_pis: str
    cst_cofins: str
    valor_icms: Decimal = Decimal("0.00")
    base_icms: Decimal = Decimal("0.00")
    aliq_icms: Decimal = Decimal("0.00")
    valor_pis: Decimal = Decimal("0.00")
    aliq_pis: Decimal = Decimal("0.00")
    valor_cofins: Decimal = Decimal("0.00")
    aliq_cofins: Decimal = Decimal("0.00")
    valor_total_tributos: Decimal = Decimal("0.00")


@dataclass
class TaxCalculationResult:
    regime: str
    items: list[ItemTax]
    base_calculo_total: Decimal
    valor_icms_total: Decimal
    valor_pis_total: Decimal
    valor_cofins_total: Decimal
    valor_total_tributos: Decimal
    valor_produtos: Decimal
    valor_servicos: Decimal
    valor_total_nf: Decimal

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "base_calculo_total": str(self.base_calculo_total),
            "valor_icms_total": str(self.valor_icms_total),
            "valor_pis_total": str(self.valor_pis_total),
            "valor_cofins_total": str(self.valor_cofins_total),
            "valor_total_tributos": str(self.valor_total_tributos),
            "valor_produtos": str(self.valor_produtos),
            "valor_servicos": str(self.valor_servicos),
            "valor_total_nf": str(self.valor_total_nf),
        }


_TWO = Decimal("0.01")
_ZERO = Decimal("0.00")

# CFOPs para oficina agrícola no Simples Nacional
_CFOP_PECA = "5949"       # Outra saída de mercadoria — uso interno/consumo
_CFOP_SERVICO = "5933"    # Prestação de serviço de manutenção e reparação

# NCM padrão para serviços (quando não informado)
_NCM_SERVICO = "00000000"
_NCM_PECA_DEFAULT = "84139100"  # Partes para bombas hidráulicas (exemplo)


def _round2(v: Decimal) -> Decimal:
    return v.quantize(_TWO, rounding=ROUND_HALF_UP)


class TaxCalculator:
    """
    Calcula os tributos dos itens da OS conforme o Simples Nacional.
    Extensível para outros regimes: basta sobrescrever `_tax_item()`.
    """

    def calculate(self, service_order: ServiceOrder) -> TaxCalculationResult:
        item_taxes: list[ItemTax] = [
            self._tax_item(item) for item in service_order.items
        ]

        _D0 = Decimal("0.00")
        valor_produtos = _round2(
            sum((t.total_price for t in item_taxes if t.item_type == ItemType.PECA), _D0)
        )
        valor_servicos = _round2(
            sum((t.total_price for t in item_taxes if t.item_type == ItemType.SERVICO), _D0)
        )
        base_total    = _round2(sum((t.base_icms           for t in item_taxes), _D0))
        icms_total    = _round2(sum((t.valor_icms          for t in item_taxes), _D0))
        pis_total     = _round2(sum((t.valor_pis           for t in item_taxes), _D0))
        cofins_total  = _round2(sum((t.valor_cofins        for t in item_taxes), _D0))
        tributos_total= _round2(sum((t.valor_total_tributos for t in item_taxes), _D0))

        return TaxCalculationResult(
            regime="Simples Nacional",
            items=item_taxes,
            base_calculo_total=base_total,
            valor_icms_total=icms_total,
            valor_pis_total=pis_total,
            valor_cofins_total=cofins_total,
            valor_total_tributos=tributos_total,
            valor_produtos=valor_produtos,
            valor_servicos=valor_servicos,
            valor_total_nf=_round2(valor_produtos + valor_servicos),
        )

    def _tax_item(self, item: ServiceOrderItem) -> ItemTax:
        is_service = item.item_type == ItemType.SERVICO
        cfop = _CFOP_SERVICO if is_service else _CFOP_PECA
        ncm = (item.ncm_code or _NCM_SERVICO) if is_service else (item.ncm_code or _NCM_PECA_DEFAULT)

        # Simples Nacional: ICMS não destacado para serviços (CSOSN 400)
        # Para peças pode usar CSOSN 102 (tributado sem crédito)
        csosn = "400" if is_service else "102"

        # Base ICMS zero para ambos no Simples (sem destaque)
        base_icms = _ZERO
        valor_icms = _ZERO
        aliq_icms = _ZERO

        # PIS/COFINS: CST 07 (isento no Simples)
        cst_pis = "07"
        cst_cofins = "07"
        aliq_pis = _ZERO
        aliq_cofins = _ZERO
        valor_pis = _ZERO
        valor_cofins = _ZERO

        # Valor total de tributos obrigatório pelo art. 1° da Lei 12.741/2012
        # Para Simples Nacional: aplica-se alíquota estimada pelo IBPT (~9,5%)
        aliq_estimada_ibpt = Decimal("0.0950")
        total = _round2(item.total_price)
        tributos = _round2(total * aliq_estimada_ibpt)

        return ItemTax(
            item_id=str(item.id),
            description=item.description,
            item_type=item.item_type,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total_price=total,
            cfop=cfop,
            ncm=ncm,
            csosn=csosn,
            cst_pis=cst_pis,
            cst_cofins=cst_cofins,
            base_icms=base_icms,
            aliq_icms=aliq_icms,
            valor_icms=valor_icms,
            aliq_pis=aliq_pis,
            valor_pis=valor_pis,
            aliq_cofins=aliq_cofins,
            valor_cofins=valor_cofins,
            valor_total_tributos=tributos,
        )


tax_calculator = TaxCalculator()
