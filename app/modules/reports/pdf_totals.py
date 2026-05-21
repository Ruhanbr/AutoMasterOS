"""
Utilitário de cálculo de totais para OS — puro e testável de forma isolada.

Não depende de sessão de DB, modelo ORM ou framework.
Recebe objetos duck-typed (item.item_type, item.total_price, order.discount).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable


@runtime_checkable
class ItemLike(Protocol):
    item_type: str
    total_price: Decimal | float | int


@runtime_checkable
class OrderLike(Protocol):
    items: list[ItemLike]
    total_discount: Decimal | float | int


ITEM_LABELS = {
    "SERVICO": "Serviço",
    "PECA": "Peça",
    "DESLOCAMENTO": "Deslocamento",
}


def calcular_totais_os(order: OrderLike) -> dict:
    """
    Calcula subtotais por tipo de item, desconto e total final.

    Retorna:
        {
            "subtotais": {
                "SERVICO": Decimal,
                "PECA": Decimal,
                "DESLOCAMENTO": Decimal,
            },
            "subtotais_labels": {"Serviço": Decimal, "Peça": Decimal, ...},
            "total_bruto": Decimal,
            "desconto": Decimal,
            "total_final": Decimal,
        }

    Exemplo de uso:
        totais = calcular_totais_os(os_instance)
        assert totais["total_final"] == totais["total_bruto"] - totais["desconto"]
    """
    subtotais: dict[str, Decimal] = {
        "SERVICO": Decimal("0.00"),
        "PECA": Decimal("0.00"),
        "DESLOCAMENTO": Decimal("0.00"),
    }

    for item in order.items:
        tipo = str(item.item_type).upper()
        valor = Decimal(str(item.total_price))
        if tipo in subtotais:
            subtotais[tipo] += valor
        else:
            # Tipos futuros caem em SERVICO por segurança
            subtotais["SERVICO"] += valor

    total_bruto = sum(subtotais.values(), Decimal("0.00"))
    desconto = Decimal(str(order.total_discount))
    total_final = total_bruto - desconto

    subtotais_labels = {
        ITEM_LABELS.get(k, k): v
        for k, v in subtotais.items()
        if v > 0  # omite zeros no relatório
    }

    return {
        "subtotais": subtotais,
        "subtotais_labels": subtotais_labels,
        "total_bruto": total_bruto,
        "desconto": desconto,
        "total_final": total_final,
    }
