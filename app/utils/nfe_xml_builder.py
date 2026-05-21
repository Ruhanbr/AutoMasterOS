"""
Construtor do XML NF-e 4.0 conforme schema oficial SEFAZ.
Namespace: http://www.portalfiscal.inf.br/nfe

Referência: Manual de Orientação ao Contribuinte NF-e v7.0
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from lxml import etree

from app.core.config import settings
from app.models.client import Client, DocumentType
from app.models.service_order import ServiceOrder
from app.models.tenant import Tenant
from app.utils.nfe_access_key import generate_access_key
from app.utils.tax_calculator import ItemTax, TaxCalculationResult

_NS = "http://www.portalfiscal.inf.br/nfe"
_NS_MAP = {None: _NS}


def _el(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    elem = etree.SubElement(parent, tag)
    if text is not None:
        elem.text = str(text)
    return elem


def _fmt2(v: Decimal) -> str:
    return f"{v:.2f}"


def _fmt4(v: Decimal) -> str:
    return f"{v:.4f}"


def _fmt10(v: Decimal) -> str:
    return f"{v:.10f}"


class NFeXMLBuilder:
    """
    Monta o XML da NF-e 4.0 a partir dos dados da OS, tenant, cliente e impostos.
    O XML produzido ainda não está assinado — a assinatura é aplicada pelo NfeSigner.
    """

    def build(
        self,
        service_order: ServiceOrder,
        tenant: Tenant,
        client: Client,
        tax_result: TaxCalculationResult,
        nfe_number: int,
        serie: int = 1,
        access_key: str | None = None,
        emissao: datetime | None = None,
    ) -> tuple[str, str]:
        """
        Retorna (xml_string, access_key).
        Gera a chave de acesso se não fornecida.
        """
        now = emissao or datetime.now(timezone.utc)
        cnpj = settings.CNPJ_EMITENTE

        chave = access_key or generate_access_key(
            uf=settings.SEFAZ_UF,
            cnpj=cnpj,
            serie=serie,
            numero=nfe_number,
            emissao=now,
        )

        nfe_id = f"NFe{chave}"

        root = etree.Element("NFe", nsmap=_NS_MAP)
        inf = etree.SubElement(root, "infNFe", versao="4.00")
        inf.set("Id", nfe_id)

        self._build_ide(inf, nfe_number, serie, chave, now)
        self._build_emit(inf, tenant, cnpj)
        self._build_dest(inf, client)

        for idx, item_tax in enumerate(tax_result.items, start=1):
            self._build_det(inf, idx, item_tax)

        self._build_total(inf, tax_result)
        self._build_transp(inf)
        self._build_pag(inf, tax_result.valor_total_nf)
        self._build_inf_adic(inf, service_order, tax_result)

        xml_bytes = etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=False)
        return xml_bytes.decode("utf-8"), chave

    # ─── ide ──────────────────────────────────────────────────────────────────

    def _build_ide(
        self,
        parent: etree._Element,
        numero: int,
        serie: int,
        chave: str,
        now: datetime,
    ) -> None:
        ide = _el(parent, "ide")
        _el(ide, "cUF", chave[:2])
        _el(ide, "cNF", chave[35:43])
        _el(ide, "natOp", "PRESTACAO DE SERVICO DE MANUTENCAO")
        _el(ide, "mod", "55")
        _el(ide, "serie", str(serie).zfill(3))
        _el(ide, "nNF", str(numero))
        _el(ide, "dhEmi", now.strftime("%Y-%m-%dT%H:%M:%S-03:00"))
        _el(ide, "dhSaiEnt", now.strftime("%Y-%m-%dT%H:%M:%S-03:00"))
        _el(ide, "tpNF", "1")       # 1=saída
        _el(ide, "idDest", "1")     # 1=operação interna
        _el(ide, "cMunFG", tenant_municipio_code(settings.SEFAZ_UF))
        _el(ide, "tpImp", "1")      # 1=DANFE retrato
        _el(ide, "tpEmis", "1")     # 1=emissão normal
        _el(ide, "cDV", chave[-1])
        _el(ide, "tpAmb", str(settings.SEFAZ_AMBIENTE))  # 1=prod, 2=homologação
        _el(ide, "finNFe", "1")     # 1=NF-e normal
        _el(ide, "indFinal", "1")   # 1=consumidor final
        _el(ide, "indPres", "1")    # 1=operação presencial
        _el(ide, "procEmi", "0")    # 0=emissão com aplicativo do contribuinte
        _el(ide, "verProc", "AutoMaster-1.0")

    # ─── emit ─────────────────────────────────────────────────────────────────

    def _build_emit(
        self, parent: etree._Element, tenant: Tenant, cnpj: str
    ) -> None:
        emit = _el(parent, "emit")
        _el(emit, "CNPJ", cnpj)
        _el(emit, "xNome", (tenant.razao_social or settings.RAZAO_SOCIAL_EMITENTE)[:60])
        if tenant.nome_fantasia:
            _el(emit, "xFant", tenant.nome_fantasia[:60])

        end_emit = _el(emit, "enderEmit")
        _el(end_emit, "xLgr", (tenant.logradouro or "RUA SEM NOME")[:60])
        _el(end_emit, "nro", (tenant.numero or "S/N")[:60])
        if tenant.complemento:
            _el(end_emit, "xCpl", tenant.complemento[:60])
        _el(end_emit, "xBairro", (tenant.bairro or "CENTRO")[:60])
        _el(end_emit, "cMun", tenant.codigo_municipio or "3550308")
        _el(end_emit, "xMun", (tenant.municipio or "SAO PAULO")[:60])
        _el(end_emit, "UF", (tenant.uf or settings.SEFAZ_UF)[:2])
        _el(end_emit, "CEP", (tenant.cep or "00000000")[:8])
        _el(end_emit, "cPais", "1058")
        _el(end_emit, "xPais", "Brasil")

        ie = tenant.inscricao_estadual or settings.IE_EMITENTE
        _el(emit, "IE", ie[:14])
        _el(emit, "CRT", settings.CRT)

    # ─── dest ─────────────────────────────────────────────────────────────────

    def _build_dest(self, parent: etree._Element, client: Client) -> None:
        dest = _el(parent, "dest")

        if client.document_type == DocumentType.CNPJ:
            _el(dest, "CNPJ", client.document)
        else:
            _el(dest, "CPF", client.document)

        _el(dest, "xNome", client.name[:60])

        end_dest = _el(dest, "enderDest")
        _el(end_dest, "xLgr", (client.logradouro or "RUA SEM NOME")[:60])
        _el(end_dest, "nro", (client.numero or "S/N")[:60])
        if client.complemento:
            _el(end_dest, "xCpl", client.complemento[:60])
        _el(end_dest, "xBairro", (client.bairro or "CENTRO")[:60])
        _el(end_dest, "cMun", client.codigo_municipio or "3550308")
        _el(end_dest, "xMun", (client.municipio or "SAO PAULO")[:60])
        _el(end_dest, "UF", (client.uf or settings.SEFAZ_UF)[:2])
        _el(end_dest, "CEP", (client.cep or "00000000")[:8])
        _el(end_dest, "cPais", "1058")
        _el(end_dest, "xPais", "Brasil")

        if client.email:
            _el(dest, "email", client.email[:60])

        # Indica tributação para consumidor final (indIEDest)
        _el(dest, "indIEDest", "9")  # 9=não contribuinte

    # ─── det ──────────────────────────────────────────────────────────────────

    def _build_det(
        self, parent: etree._Element, idx: int, item: ItemTax
    ) -> None:
        det = etree.SubElement(parent, "det", nItem=str(idx))
        prod = _el(det, "prod")
        _el(prod, "cProd", str(idx).zfill(6))
        _el(prod, "cEAN", "SEM GTIN")
        _el(prod, "xProd", item.description[:120])
        _el(prod, "NCM", item.ncm.replace(".", "")[:8])
        _el(prod, "CFOP", item.cfop)
        _el(prod, "uCom", "UN")
        _el(prod, "qCom", _fmt4(item.quantity))
        _el(prod, "vUnCom", _fmt10(item.unit_price))
        _el(prod, "vProd", _fmt2(item.total_price))
        _el(prod, "cEANTrib", "SEM GTIN")
        _el(prod, "uTrib", "UN")
        _el(prod, "qTrib", _fmt4(item.quantity))
        _el(prod, "vUnTrib", _fmt10(item.unit_price))
        _el(prod, "indTot", "1")

        imposto = _el(det, "imposto")
        _el(imposto, "vTotTrib", _fmt2(item.valor_total_tributos))

        # ICMS — Simples Nacional
        icms_el = _el(imposto, "ICMS")
        if item.csosn in {"400", "102"}:
            csosn_el = _el(icms_el, f"ICMSSN{item.csosn}")
            _el(csosn_el, "orig", "0")      # 0=Nacional
            _el(csosn_el, "CSOSN", item.csosn)

        # PIS
        pis_el = _el(imposto, "PIS")
        pis_nt = _el(pis_el, "PISNT")
        _el(pis_nt, "CST", item.cst_pis)

        # COFINS
        cofins_el = _el(imposto, "COFINS")
        cofins_nt = _el(cofins_el, "COFINSNT")
        _el(cofins_nt, "CST", item.cst_cofins)

    # ─── total ────────────────────────────────────────────────────────────────

    def _build_total(
        self, parent: etree._Element, tax: TaxCalculationResult
    ) -> None:
        total = _el(parent, "total")
        icms_tot = _el(total, "ICMSTot")
        _el(icms_tot, "vBC", _fmt2(tax.base_calculo_total))
        _el(icms_tot, "vICMS", _fmt2(tax.valor_icms_total))
        _el(icms_tot, "vICMSDeson", "0.00")
        _el(icms_tot, "vFCP", "0.00")
        _el(icms_tot, "vBCST", "0.00")
        _el(icms_tot, "vST", "0.00")
        _el(icms_tot, "vFCPST", "0.00")
        _el(icms_tot, "vFCPSTRet", "0.00")
        _el(icms_tot, "vProd", _fmt2(tax.valor_total_nf))
        _el(icms_tot, "vFrete", "0.00")
        _el(icms_tot, "vSeg", "0.00")
        _el(icms_tot, "vDesc", "0.00")
        _el(icms_tot, "vII", "0.00")
        _el(icms_tot, "vIPI", "0.00")
        _el(icms_tot, "vIPIDevol", "0.00")
        _el(icms_tot, "vPIS", _fmt2(tax.valor_pis_total))
        _el(icms_tot, "vCOFINS", _fmt2(tax.valor_cofins_total))
        _el(icms_tot, "vOutro", "0.00")
        _el(icms_tot, "vNF", _fmt2(tax.valor_total_nf))
        _el(icms_tot, "vTotTrib", _fmt2(tax.valor_total_tributos))

    # ─── transp ───────────────────────────────────────────────────────────────

    def _build_transp(self, parent: etree._Element) -> None:
        transp = _el(parent, "transp")
        _el(transp, "modFrete", "9")  # 9=sem frete (serviço)

    # ─── pag ──────────────────────────────────────────────────────────────────

    def _build_pag(self, parent: etree._Element, total: Decimal) -> None:
        pag = _el(parent, "pag")
        det_pag = _el(pag, "detPag")
        _el(det_pag, "tPag", "01")    # 01=dinheiro (padrão genérico)
        _el(det_pag, "vPag", _fmt2(total))

    # ─── infAdic ──────────────────────────────────────────────────────────────

    def _build_inf_adic(
        self,
        parent: etree._Element,
        service_order: ServiceOrder,
        tax: TaxCalculationResult,
    ) -> None:
        inf_adic = _el(parent, "infAdic")
        obs = (
            f"OS #{service_order.number} | "
            f"Regime: Simples Nacional | "
            f"Valor aprox. tributos: R$ {tax.valor_total_tributos:.2f} "
            f"({100 * float(tax.valor_total_tributos / tax.valor_total_nf):.1f}%) "
            f"Fonte: IBPT"
        )
        if settings.SEFAZ_AMBIENTE == 2:
            obs = "NOTA EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL | " + obs
        _el(inf_adic, "infCpl", obs[:2000])


def tenant_municipio_code(uf: str) -> str:
    """Código IBGE do município padrão por UF (fallback para SP)."""
    defaults = {"SP": "3550308", "MG": "3106200", "RS": "4314902", "PR": "4106902"}
    return defaults.get(uf.upper(), "3550308")


nfe_xml_builder = NFeXMLBuilder()
