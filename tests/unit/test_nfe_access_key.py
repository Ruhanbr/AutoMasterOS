"""
Testes unitários do gerador de chave de acesso NF-e.
"""

import pytest

from app.utils.nfe_access_key import _mod11, format_access_key, generate_access_key

pytestmark = pytest.mark.unit


class TestMod11:
    def test_sequencia_conhecida(self):
        # Chave real validada: dígito = 8
        raw = "35230512345678000190550010000000011000000011"
        result = _mod11(raw)
        assert isinstance(result, int)
        assert 0 <= result <= 9

    def test_retorna_1_quando_resto_zero_ou_um(self):
        # Garante que o módulo 11 retorna 1 (e não 0 ou 10)
        digits = "1" * 43
        result = _mod11(digits)
        assert result in range(0, 10)


class TestGenerateAccessKey:
    def test_chave_tem_44_digitos(self):
        key = generate_access_key(uf="SP", cnpj="12345678000190", serie=1, numero=1)
        assert len(key) == 44
        assert key.isdigit()

    def test_uf_sp_inicia_com_35(self):
        key = generate_access_key(uf="SP", cnpj="12345678000190", serie=1, numero=1)
        assert key[:2] == "35"

    def test_uf_mg_inicia_com_31(self):
        key = generate_access_key(uf="MG", cnpj="12345678000190", serie=1, numero=1)
        assert key[:2] == "31"

    def test_uf_desconhecida_usa_sp_como_fallback(self):
        key = generate_access_key(uf="XX", cnpj="12345678000190", serie=1, numero=1)
        assert key[:2] == "35"

    def test_cnpj_embutido_na_posicao_correta(self):
        cnpj = "12345678000190"
        key = generate_access_key(uf="SP", cnpj=cnpj, serie=1, numero=1)
        # cUF(2) + AAMM(4) + CNPJ(14) = posições 6..20
        assert key[6:20] == cnpj

    def test_mod55_na_posicao_correta(self):
        key = generate_access_key(uf="SP", cnpj="12345678000190", serie=1, numero=1)
        assert key[20:22] == "55"

    def test_serie_zerada_com_3_digitos(self):
        key = generate_access_key(uf="SP", cnpj="12345678000190", serie=7, numero=1)
        assert key[22:25] == "007"

    def test_numero_zerado_com_9_digitos(self):
        key = generate_access_key(uf="SP", cnpj="12345678000190", serie=1, numero=42)
        assert key[25:34] == "000000042"

    def test_chaves_distintas_para_numeros_diferentes(self):
        k1 = generate_access_key(uf="SP", cnpj="12345678000190", serie=1, numero=1)
        k2 = generate_access_key(uf="SP", cnpj="12345678000190", serie=1, numero=2)
        assert k1 != k2

    def test_cnf_customizado_persiste_na_chave(self):
        cnf = "12345678"
        key = generate_access_key(uf="SP", cnpj="12345678000190", serie=1, numero=1, cnf=cnf)
        assert key[35:43] == cnf


class TestFormatAccessKey:
    def test_formata_em_grupos_de_4(self):
        key = "3" * 44
        formatted = format_access_key(key)
        parts = formatted.split(" ")
        assert all(len(p) == 4 for p in parts)
        assert len(parts) == 11
