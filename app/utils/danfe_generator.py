"""
Gerador de DANFE (Documento Auxiliar da NF-e) em PDF usando ReportLab.
Produz um layout simplificado porém completo para uso em oficinas agrícolas.
"""

import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.models.invoice import Invoice
from app.models.service_order import ServiceOrder
from app.utils.nfe_access_key import format_access_key
from app.utils.tax_calculator import TaxCalculationResult

logger = get_logger(__name__)

_GRAY = colors.HexColor("#4A4A4A")
_LIGHT_GRAY = colors.HexColor("#F2F2F2")
_DARK_GRAY = colors.HexColor("#2C2C2C")
_BLUE = colors.HexColor("#003366")
_W, _H = A4


def _fmt_currency(v: Decimal) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_date(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    local = dt.astimezone()
    return local.strftime("%d/%m/%Y %H:%M")


class DanfeGenerator:
    def generate(
        self,
        service_order: ServiceOrder,
        invoice: Invoice,
        tax_result: TaxCalculationResult,
    ) -> str:
        """
        Gera o PDF do DANFE e persiste em disco.
        Retorna o caminho absoluto do arquivo gerado.
        """
        output_dir = Path(settings.DANFE_OUTPUT_PATH)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"danfe_{invoice.access_key or str(invoice.id)}.pdf"
        output_path = output_dir / filename

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=10 * mm,
            leftMargin=10 * mm,
            topMargin=10 * mm,
            bottomMargin=10 * mm,
        )

        styles = getSampleStyleSheet()
        story = []

        story.extend(self._header_section(invoice, styles))
        story.append(Spacer(1, 4 * mm))
        story.extend(self._identification_section(invoice, service_order))
        story.append(Spacer(1, 4 * mm))
        story.extend(self._emitter_recipient_section(service_order))
        story.append(Spacer(1, 4 * mm))
        story.extend(self._items_table(tax_result, styles))
        story.append(Spacer(1, 4 * mm))
        story.extend(self._totals_section(tax_result))
        story.append(Spacer(1, 4 * mm))
        story.extend(self._additional_info(service_order, invoice))

        doc.build(story)

        logger.info(
            "danfe_gerado",
            invoice_id=str(invoice.id),
            path=str(output_path),
        )
        return str(output_path)

    def _header_section(self, invoice: Invoice, styles) -> list:
        title_style = ParagraphStyle(
            "DanfeTitle",
            fontSize=11,
            fontName="Helvetica-Bold",
            textColor=_BLUE,
            alignment=1,
        )
        sub_style = ParagraphStyle(
            "DanfeSub",
            fontSize=8,
            fontName="Helvetica",
            textColor=_GRAY,
            alignment=1,
        )
        amb = "HOMOLOGAÇÃO - SEM VALOR FISCAL" if settings.SEFAZ_AMBIENTE == 2 else "DOCUMENTO AUXILIAR DA NF-e"

        header_data = [
            [
                Paragraph(f"<b>{settings.RAZAO_SOCIAL_EMITENTE}</b>", title_style),
                Paragraph("DANFE", title_style),
                Paragraph(f"NF-e N°: <b>{invoice.number or '-'}</b><br/>Série: <b>{invoice.series}</b>", sub_style),
            ],
            [
                Paragraph(f"CNPJ: {settings.CNPJ_EMITENTE}", sub_style),
                Paragraph(amb, sub_style),
                Paragraph(f"Folha 1/1", sub_style),
            ],
        ]
        table = Table(header_data, colWidths=[85 * mm, 75 * mm, 30 * mm])
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, _DARK_GRAY),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, _GRAY),
            ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return [table]

    def _identification_section(self, invoice: Invoice, service_order: ServiceOrder) -> list:
        key = invoice.access_key or "CHAVE NAO DISPONIVEL"
        style = ParagraphStyle("ident", fontSize=7, fontName="Helvetica", alignment=1)
        data = [
            [Paragraph(f"<b>CHAVE DE ACESSO</b>", style)],
            [Paragraph(format_access_key(key), style)],
            [Paragraph(
                f"Protocolo: {invoice.protocol_number or '-'} | "
                f"Autorizado em: {_fmt_date(invoice.authorized_at)}",
                style,
            )],
        ]
        table = Table(data, colWidths=[190 * mm])
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, _DARK_GRAY),
            ("BACKGROUND", (0, 0), (0, 0), _LIGHT_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return [table]

    def _emitter_recipient_section(self, service_order: ServiceOrder) -> list:
        client = service_order.client
        style7 = ParagraphStyle("cell7", fontSize=7, fontName="Helvetica")

        emit_info = (
            f"<b>EMITENTE</b><br/>"
            f"{settings.RAZAO_SOCIAL_EMITENTE}<br/>"
            f"CNPJ: {settings.CNPJ_EMITENTE}<br/>"
            f"IE: {settings.IE_EMITENTE}"
        )
        client_info = (
            f"<b>DESTINATÁRIO</b><br/>"
            f"{client.name if client else '-'}<br/>"
            f"Doc: {client.document if client else '-'}<br/>"
            f"Município: {client.municipio or '-'} / {client.uf or '-'}"
        )
        data = [[Paragraph(emit_info, style7), Paragraph(client_info, style7)]]
        table = Table(data, colWidths=[95 * mm, 95 * mm])
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, _DARK_GRAY),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, _GRAY),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return [table]

    def _items_table(self, tax_result: TaxCalculationResult, styles) -> list:
        header_style = ParagraphStyle("th", fontSize=7, fontName="Helvetica-Bold", alignment=1)
        cell_style = ParagraphStyle("td", fontSize=6, fontName="Helvetica")

        header = [
            Paragraph("Nº", header_style),
            Paragraph("Descrição", header_style),
            Paragraph("NCM", header_style),
            Paragraph("CFOP", header_style),
            Paragraph("Qtde", header_style),
            Paragraph("V.Unit.", header_style),
            Paragraph("V.Total", header_style),
        ]
        rows = [header]
        for idx, item in enumerate(tax_result.items, 1):
            rows.append([
                Paragraph(str(idx), cell_style),
                Paragraph(item.description[:60], cell_style),
                Paragraph(item.ncm, cell_style),
                Paragraph(item.cfop, cell_style),
                Paragraph(f"{item.quantity:.3f}", cell_style),
                Paragraph(_fmt_currency(item.unit_price), cell_style),
                Paragraph(_fmt_currency(item.total_price), cell_style),
            ])

        col_w = [8 * mm, 75 * mm, 20 * mm, 15 * mm, 18 * mm, 27 * mm, 27 * mm]
        table = Table(rows, colWidths=col_w, repeatRows=1)
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, _DARK_GRAY),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, _GRAY),
            ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_GRAY]),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return [table]

    def _totals_section(self, tax_result: TaxCalculationResult) -> list:
        style = ParagraphStyle("tot", fontSize=8, fontName="Helvetica", alignment=2)
        bold = ParagraphStyle("tot_bold", fontSize=9, fontName="Helvetica-Bold", alignment=2)
        data = [
            [Paragraph("Valor Serviços:", style), Paragraph(_fmt_currency(tax_result.valor_servicos), style)],
            [Paragraph("Valor Peças:", style), Paragraph(_fmt_currency(tax_result.valor_produtos), style)],
            [Paragraph("ICMS:", style), Paragraph(_fmt_currency(tax_result.valor_icms_total), style)],
            [Paragraph("PIS:", style), Paragraph(_fmt_currency(tax_result.valor_pis_total), style)],
            [Paragraph("COFINS:", style), Paragraph(_fmt_currency(tax_result.valor_cofins_total), style)],
            [Paragraph("<b>TOTAL NF-e:</b>", bold), Paragraph(_fmt_currency(tax_result.valor_total_nf), bold)],
        ]
        table = Table(data, colWidths=[140 * mm, 50 * mm])
        table.setStyle(TableStyle([
            ("BOX", (0, -1), (-1, -1), 1, _BLUE),
            ("LINEABOVE", (0, -1), (-1, -1), 1, _BLUE),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return [table]

    def _additional_info(self, service_order: ServiceOrder, invoice: Invoice) -> list:
        style = ParagraphStyle("info", fontSize=7, fontName="Helvetica")
        info = (
            f"<b>Informações Adicionais</b><br/>"
            f"OS: #{service_order.number} | "
            f"Regime: Simples Nacional | "
            f"{'AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL' if settings.SEFAZ_AMBIENTE == 2 else ''}"
        )
        if service_order.description:
            info += f"<br/>Descrição: {service_order.description[:200]}"
        data = [[Paragraph(info, style)]]
        table = Table(data, colWidths=[190 * mm])
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, _DARK_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return [table]


danfe_generator = DanfeGenerator()
