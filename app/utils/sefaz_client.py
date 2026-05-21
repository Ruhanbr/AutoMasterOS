"""
Cliente SEFAZ com suporte a modo real (SOAP/HTTPS) e mock.

O mock simula fielmente os retornos da SEFAZ para:
  - Autorização (cStat 100)
  - Rejeição de negócio (cStat 204 — duplicidade de NF)
  - Rejeição de schema (cStat 214)

Ativação: SEFAZ_MOCK_ENABLED=true em .env
"""

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SefazResponse:
    authorized: bool
    access_key: str
    protocol_number: str | None = None
    status_code: str = "100"
    status_message: str = "Autorizado o uso da NF-e"
    rejection_code: str | None = None
    rejection_message: str | None = None
    raw_response: str | None = None


class SefazCommunicationError(Exception):
    """Falha de rede/timeout com a SEFAZ — elegível para retry."""


class SefazRejectionError(Exception):
    """SEFAZ rejeitou a NF por regra de negócio — NÃO fazer retry automático."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"SEFAZ rejeição {code}: {message}")


# ─── Mock ─────────────────────────────────────────────────────────────────────

class SefazMockClient:
    """
    Simula a SEFAZ para ambiente de desenvolvimento/testes.
    Controlado por SEFAZ_MOCK_ENABLED=true.

    Comportamentos configuráveis via variável de instância (para testes):
      - force_rejection: força rejeição
      - force_error: força erro de comunicação
    """

    force_rejection: bool = False
    force_error: bool = False
    rejection_code: str = "204"
    rejection_message: str = "Duplicidade de NF-e"

    async def authorize(self, xml_signed: str, access_key: str) -> SefazResponse:
        # Simula latência de rede (~200-800ms)
        await asyncio.sleep(random.uniform(0.2, 0.8))

        logger.info(
            "sefaz_mock_chamado",
            access_key=access_key,
            force_rejection=self.force_rejection,
            force_error=self.force_error,
        )

        if self.force_error:
            raise SefazCommunicationError("Mock: erro de comunicação simulado")

        if self.force_rejection:
            raise SefazRejectionError(self.rejection_code, self.rejection_message)

        protocol = f"1{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}{random.randint(100000000, 999999999)}"

        logger.info(
            "sefaz_mock_autorizado",
            access_key=access_key,
            protocol=protocol,
        )

        return SefazResponse(
            authorized=True,
            access_key=access_key,
            protocol_number=protocol,
            status_code="100",
            status_message="Autorizado o uso da NF-e",
            raw_response=self._build_mock_response(access_key, protocol),
        )

    def _build_mock_response(self, access_key: str, protocol: str) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S-03:00")
        return (
            f'<retEnviNFe versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">'
            f'<tpAmb>2</tpAmb><verAplic>SP_NFE_PL009_V4.00</verAplic>'
            f'<cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo>'
            f'<cUF>35</cUF><dhRecbto>{now}</dhRecbto>'
            f'<protNFe versao="4.00"><infProt>'
            f'<tpAmb>2</tpAmb><verAplic>SP_NFE_PL009_V4.00</verAplic>'
            f'<chNFe>{access_key}</chNFe><dhRecbto>{now}</dhRecbto>'
            f'<nProt>{protocol}</nProt><digVal>placeholder=</digVal>'
            f'<cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo>'
            f'</infProt></protNFe></retEnviNFe>'
        )


# ─── Cliente Real ─────────────────────────────────────────────────────────────

class SefazHttpClient:
    """
    Cliente SOAP para ambiente de produção/homologação real.
    Usa httpx com timeout configurável.
    """

    _SOAP_ACTION = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4/nfeAutorizacaoLote"

    async def authorize(self, xml_signed: str, access_key: str) -> SefazResponse:
        envelope = self._build_soap_envelope(xml_signed, access_key)

        try:
            async with httpx.AsyncClient(
                verify=False,
                timeout=settings.SEFAZ_TIMEOUT,
            ) as client:
                response = await client.post(
                    settings.SEFAZ_WEBSERVICE_URL,
                    content=envelope.encode("utf-8"),
                    headers={
                        "Content-Type": "application/soap+xml; charset=utf-8",
                        "SOAPAction": self._SOAP_ACTION,
                    },
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.error("sefaz_timeout", access_key=access_key, error=str(exc))
            raise SefazCommunicationError(f"Timeout na comunicação com SEFAZ: {exc}") from exc
        except httpx.HTTPError as exc:
            logger.error("sefaz_http_error", access_key=access_key, error=str(exc))
            raise SefazCommunicationError(f"Erro HTTP SEFAZ: {exc}") from exc

        return self._parse_response(response.text, access_key)

    def _build_soap_envelope(self, xml_signed: str, access_key: str) -> str:
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
            "<soap12:Body>"
            '<nfeAutorizacaoLote xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4">'
            "<nfeDadosMsg>"
            f'<enviNFe versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">'
            f"<idLote>1</idLote><indSinc>1</indSinc>{xml_signed}</enviNFe>"
            "</nfeDadosMsg>"
            "</nfeAutorizacaoLote>"
            "</soap12:Body>"
            "</soap12:Envelope>"
        )

    def _parse_response(self, response_text: str, access_key: str) -> SefazResponse:
        from lxml import etree

        ns = "http://www.portalfiscal.inf.br/nfe"
        root = etree.fromstring(response_text.encode("utf-8"))

        c_stat_el = root.find(f".//{{{ns}}}cStat")
        x_motivo_el = root.find(f".//{{{ns}}}xMotivo")
        n_prot_el = root.find(f".//{{{ns}}}nProt")

        c_stat = c_stat_el.text if c_stat_el is not None else "999"
        x_motivo = x_motivo_el.text if x_motivo_el is not None else "Erro desconhecido"
        n_prot = n_prot_el.text if n_prot_el is not None else None

        if c_stat == "100":
            return SefazResponse(
                authorized=True,
                access_key=access_key,
                protocol_number=n_prot,
                status_code=c_stat,
                status_message=x_motivo,
                raw_response=response_text,
            )

        # Rejeições de negócio (200-299) não devem gerar retry automático
        if 200 <= int(c_stat) <= 299:
            raise SefazRejectionError(c_stat, x_motivo)

        # Outros erros (schema, comunicação) — retry
        raise SefazCommunicationError(f"SEFAZ cStat={c_stat}: {x_motivo}")


# ─── Factory ──────────────────────────────────────────────────────────────────

def get_sefaz_client() -> SefazMockClient | SefazHttpClient:
    if settings.SEFAZ_MOCK_ENABLED:
        return SefazMockClient()
    return SefazHttpClient()
