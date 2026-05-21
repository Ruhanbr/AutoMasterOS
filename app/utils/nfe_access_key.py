"""
Gerador de chave de acesso NF-e (44 dígitos) e número sequencial de NF.

Estrutura da chave (NT 2011/004):
  cUF(2) + AAMM(4) + CNPJ(14) + mod(2) + serie(3) + nNF(9) + tpEmis(1) + cNF(8) + cDV(1)
"""

import random
import string
from datetime import datetime, timezone


_UF_CODE = {
    "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29",
    "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
    "MT": "51", "MS": "50", "MG": "31", "PA": "15", "PB": "25",
    "PR": "41", "PE": "26", "PI": "22", "RJ": "33", "RN": "24",
    "RS": "43", "RO": "11", "RR": "14", "SC": "42", "SP": "35",
    "SE": "28", "TO": "17",
}


def _mod11(digits: str) -> int:
    """Dígito verificador por módulo 11 conforme manual SEFAZ."""
    weights = list(range(2, 10)) * 6  # 2..9 repetido
    total = sum(int(d) * w for d, w in zip(reversed(digits), weights))
    remainder = total % 11
    return 1 if remainder in {0, 1} else 11 - remainder


def _random_cnf() -> str:
    """Código numérico aleatório de 8 dígitos (cNF)."""
    return "".join(random.choices(string.digits, k=8))


def generate_access_key(
    uf: str,
    cnpj: str,
    serie: int,
    numero: int,
    tp_emis: str = "1",
    cnf: str | None = None,
    emissao: datetime | None = None,
) -> str:
    """
    Gera a chave de acesso de 44 dígitos da NF-e.

    Args:
        uf:      Sigla do estado emitente (ex.: "SP")
        cnpj:    CNPJ do emitente (somente dígitos, 14 chars)
        serie:   Série da NF-e (1-999)
        numero:  Número da NF-e (1-999999999)
        tp_emis: Tipo de emissão (1=normal, 9=contingência offline)
        cnf:     Código numérico aleatório (gerado automaticamente se None)
        emissao: Data/hora de emissão (UTC agora se None)
    """
    c_uf = _UF_CODE.get(uf.upper(), "35")
    ref = emissao or datetime.now(timezone.utc)
    aamm = ref.strftime("%y%m")
    mod = "55"
    serie_str = str(serie).zfill(3)
    nnf_str = str(numero).zfill(9)
    cnf_str = cnf or _random_cnf()

    raw = c_uf + aamm + cnpj + mod + serie_str + nnf_str + tp_emis + cnf_str
    cdv = _mod11(raw)
    return raw + str(cdv)


def format_access_key(key: str) -> str:
    """Formata chave para exibição: grupos de 4 dígitos."""
    return " ".join(key[i:i+4] for i in range(0, len(key), 4))


def get_uf_code(uf: str) -> str:
    return _UF_CODE.get(uf.upper(), "35")
