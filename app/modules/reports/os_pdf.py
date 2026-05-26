"""
OS PDF generator using ReportLab.

Generates a professional A4 PDF for a Service Order (Ordem de Serviço).
"""
import io
from datetime import datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Color palette
COLOR_PRIMARY = colors.HexColor("#1a5276")
COLOR_SECONDARY = colors.HexColor("#2e86c1")
COLOR_ACCENT = colors.HexColor("#f39c12")
COLOR_LIGHT_GRAY = colors.HexColor("#f2f3f4")
COLOR_DARK_GRAY = colors.HexColor("#566573")
COLOR_SUCCESS = colors.HexColor("#1e8449")


def _status_color(status: str) -> colors.Color:
    mapping = {
        "ABERTA": colors.HexColor("#2980b9"),
        "EM_ANDAMENTO": colors.HexColor("#d35400"),
        "FINALIZADA": COLOR_SUCCESS,
    }
    return mapping.get(status, COLOR_DARK_GRAY)


def _fmt_currency(value) -> str:
    if value is None:
        return "0,00"
    try:
        d = Decimal(str(value))
        return f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00"


def _fmt_datetime(dt) -> str:
    if dt is None:
        return "—"
    if isinstance(dt, str):
        return dt
    try:
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(dt)


def _fmt_date(dt) -> str:
    if dt is None:
        return "—"
    if isinstance(dt, str):
        return dt[:10]
    try:
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(dt)


def _load_signature_image(url: str | None, width: int = 120, height: int = 50) -> Image | None:
    """
    Carrega imagem de assinatura a partir de:
      - data URI base64 (data:image/png;base64,...)  ← assinatura do cliente (canvas)
      - URL HTTP(S)                                   ← assinatura do técnico
      - path local                                    ← uso interno/testes
    Retorna None se inválido.
    """
    if not url:
        return None
    try:
        import base64
        import os
        import urllib.request

        if url.startswith("data:"):
            # base64 data URI: extrai a parte binária e cria buffer em memória
            header, encoded = url.split(",", 1)
            img_bytes = base64.b64decode(encoded)
            source = io.BytesIO(img_bytes)
        elif url.startswith(("http://", "https://")):
            tmp_path = f"/tmp/sig_{abs(hash(url))}.img"
            if not os.path.exists(tmp_path):
                urllib.request.urlretrieve(url, tmp_path)
            source = tmp_path
        else:
            if not os.path.exists(url):
                return None
            source = url

        return Image(source, width=width, height=height, kind="proportional")
    except Exception:
        return None


def generate_os_pdf(order_data: dict) -> bytes:
    """
    Generate a professional OS PDF.

    order_data keys:
      os_number, status, opened_at, finished_at, technician_name,
      technician_signature_url (opcional — path local ou URL),
      description, diagnosis, solution, client_name, client_document, client_phone,
      machine_model, machine_brand, machine_serial (optional),
      items: list[{item_type, description, quantity, unit_price, total_price}],
      total_services, total_parts, total_displacement, total_discount, total_amount,
      tenant_name, generated_at
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"OS #{order_data.get('os_number', '')}",
        author=order_data.get("tenant_name", "AutoMaster"),
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Normal"],
        fontSize=18,
        fontName="Helvetica-Bold",
        textColor=COLOR_PRIMARY,
        alignment=TA_LEFT,
        spaceAfter=2 * mm,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica",
        textColor=COLOR_DARK_GRAY,
        alignment=TA_LEFT,
    )
    section_header_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        alignment=TA_LEFT,
    )
    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=8,
        fontName="Helvetica-Bold",
        textColor=COLOR_DARK_GRAY,
    )
    value_style = ParagraphStyle(
        "Value",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica",
        textColor=colors.black,
    )
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=7,
        fontName="Helvetica",
        textColor=COLOR_DARK_GRAY,
        alignment=TA_CENTER,
    )
    total_style = ParagraphStyle(
        "Total",
        parent=styles["Normal"],
        fontSize=12,
        fontName="Helvetica-Bold",
        textColor=COLOR_PRIMARY,
        alignment=TA_RIGHT,
    )

    story = []
    page_width = A4[0] - 30 * mm  # usable width

    # ── HEADER ────────────────────────────────────────────────────────────────
    tenant_name = order_data.get("tenant_name", "AutoMaster Oficina")
    tenant_doc = order_data.get("tenant_document", "")
    tenant_phone = order_data.get("tenant_phone", "")
    tenant_email = order_data.get("tenant_email", "")
    tenant_addr = order_data.get("tenant_address", "")
    tenant_logo_url = order_data.get("tenant_logo_url")
    os_number = order_data.get("os_number", "")
    status = order_data.get("status", "")
    status_color = _status_color(status)

    # Monta bloco de informações da oficina
    oficina_lines = [Paragraph(f"<b>{tenant_name}</b>", title_style)]
    if tenant_doc:
        label = "CPF" if len(str(tenant_doc).replace(".", "").replace("-", "").replace("/", "")) == 11 else "CNPJ"
        oficina_lines.append(Paragraph(f"{label}: {tenant_doc}", subtitle_style))
    if tenant_phone:
        oficina_lines.append(Paragraph(f"Tel: {tenant_phone}", subtitle_style))
    if tenant_email:
        oficina_lines.append(Paragraph(f"E-mail: {tenant_email}", subtitle_style))
    if tenant_addr:
        oficina_lines.append(Paragraph(tenant_addr, subtitle_style))

    from reportlab.platypus import KeepTogether

    # Logo: usa a imagem da oficina se disponível, senão bloco colorido
    logo_img = _load_signature_image(tenant_logo_url) if tenant_logo_url else None
    if logo_img:
        logo_img.drawWidth = 20 * mm
        logo_img.drawHeight = 20 * mm
        logo_img.kind = "proportional"
        logo_cell = logo_img
    else:
        logo_cell = Table(
            [[""]],
            colWidths=[20 * mm],
            rowHeights=[20 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_PRIMARY),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]),
        )

    header_data = [
        [
            logo_cell,
            oficina_lines,
            Paragraph(
                f"<b>OS #{os_number}</b>",
                ParagraphStyle("OSNum", parent=title_style, fontSize=16, alignment=TA_RIGHT),
            ),
        ]
    ]

    header_table = Table(
        header_data,
        colWidths=[22 * mm, page_width - 55 * mm, 33 * mm],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]),
    )
    story.append(header_table)
    story.append(Spacer(1, 3 * mm))

    # Status badge
    status_table = Table(
        [[Paragraph(f"Status: {status}", ParagraphStyle(
            "StatusBadge",
            parent=styles["Normal"],
            fontSize=10,
            fontName="Helvetica-Bold",
            textColor=colors.white,
            alignment=TA_CENTER,
        ))]],
        colWidths=[page_width],
        rowHeights=[8 * mm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), status_color),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROUNDEDCORNERS", [3]),
        ]),
    )
    story.append(status_table)
    story.append(Spacer(1, 4 * mm))

    # ── OS INFO ───────────────────────────────────────────────────────────────
    info_data = [
        [
            Paragraph("Abertura:", label_style),
            Paragraph(_fmt_datetime(order_data.get("opened_at")), value_style),
            Paragraph("Finalização:", label_style),
            Paragraph(_fmt_datetime(order_data.get("finished_at")), value_style),
        ],
        [
            Paragraph("Técnico:", label_style),
            Paragraph(str(order_data.get("technician_name") or "—"), value_style),
            Paragraph("", label_style),
            Paragraph("", value_style),
        ],
    ]
    if order_data.get("description"):
        info_data.append([
            Paragraph("Descrição:", label_style),
            Paragraph(str(order_data.get("description", "")), value_style),
            Paragraph("", label_style),
            Paragraph("", value_style),
        ])

    col_w = page_width / 4
    info_table = Table(
        info_data,
        colWidths=[col_w * 0.6, col_w * 1.4, col_w * 0.6, col_w * 1.4],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT_GRAY),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.white),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]),
    )
    story.append(info_table)
    story.append(Spacer(1, 4 * mm))

    # ── CLIENT SECTION ────────────────────────────────────────────────────────
    client_header = Table(
        [[Paragraph("  CLIENTE", section_header_style)]],
        colWidths=[page_width],
        rowHeights=[7 * mm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_SECONDARY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]),
    )
    story.append(client_header)

    client_phone = str(order_data.get("client_phone") or "—")
    client_phone2 = order_data.get("client_phone_secondary")
    client_fazenda = order_data.get("client_fazenda")
    client_address = order_data.get("client_address")
    client_ie = order_data.get("client_inscricao_estadual")

    client_data = [
        [
            Paragraph("Nome:", label_style),
            Paragraph(str(order_data.get("client_name", "—")), value_style),
            Paragraph("Documento:", label_style),
            Paragraph(str(order_data.get("client_document", "—")), value_style),
        ],
        [
            Paragraph("Telefone:", label_style),
            Paragraph(client_phone, value_style),
            Paragraph("Tel. Secundário:" if client_phone2 else "", label_style),
            Paragraph(str(client_phone2 or ""), value_style),
        ],
    ]

    if client_fazenda:
        client_data.append([
            Paragraph("Fazenda:", label_style),
            Paragraph(str(client_fazenda), value_style),
            Paragraph("", label_style),
            Paragraph("", value_style),
        ])

    if client_address:
        client_data.append([
            Paragraph("Endereço:", label_style),
            Paragraph(str(client_address), ParagraphStyle("addr", parent=value_style, fontSize=8)),
            Paragraph("", label_style),
            Paragraph("", value_style),
        ])

    if client_ie:
        client_data.append([
            Paragraph("Insc. Estadual:", label_style),
            Paragraph(str(client_ie), value_style),
            Paragraph("", label_style),
            Paragraph("", value_style),
        ])

    client_table = Table(
        client_data,
        colWidths=[col_w * 0.6, col_w * 1.4, col_w * 0.6, col_w * 1.4],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT_GRAY),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.white),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]),
    )
    story.append(client_table)
    story.append(Spacer(1, 4 * mm))

    # ── MACHINE SECTION (if present) ──────────────────────────────────────────
    if order_data.get("machine_model") or order_data.get("machine_brand"):
        machine_header = Table(
            [[Paragraph("  MÁQUINA / EQUIPAMENTO", section_header_style)]],
            colWidths=[page_width],
            rowHeights=[7 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_SECONDARY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]),
        )
        story.append(machine_header)

        machine_chassis = order_data.get("machine_chassis")
        machine_placa = order_data.get("machine_placa")
        machine_proprietario = order_data.get("machine_proprietario")
        machine_year = order_data.get("machine_year")
        machine_hp = order_data.get("machine_horsepower")
        machine_engine = order_data.get("machine_engine_number")

        machine_data = [
            [
                Paragraph("Marca:", label_style),
                Paragraph(str(order_data.get("machine_brand", "—")), value_style),
                Paragraph("Modelo:", label_style),
                Paragraph(str(order_data.get("machine_model", "—")), value_style),
            ],
            [
                Paragraph("Nº de Série:", label_style),
                Paragraph(str(order_data.get("machine_serial") or "—"), value_style),
                Paragraph("Ano:", label_style),
                Paragraph(str(machine_year) if machine_year else "—", value_style),
            ],
        ]

        if machine_chassis or machine_placa:
            machine_data.append([
                Paragraph("Chassi:", label_style),
                Paragraph(str(machine_chassis or "—"), value_style),
                Paragraph("Placa:", label_style),
                Paragraph(str(machine_placa or "—"), value_style),
            ])

        if machine_proprietario:
            machine_data.append([
                Paragraph("Proprietário:", label_style),
                Paragraph(str(machine_proprietario), value_style),
                Paragraph("", label_style),
                Paragraph("", value_style),
            ])

        if machine_engine or machine_hp:
            machine_data.append([
                Paragraph("Nº Motor:", label_style),
                Paragraph(str(machine_engine or "—"), value_style),
                Paragraph("Potência:", label_style),
                Paragraph(str(machine_hp or "—"), value_style),
            ])

        machine_table = Table(
            machine_data,
            colWidths=[col_w * 0.55, col_w * 1.45, col_w * 0.55, col_w * 1.45],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT_GRAY),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]),
        )
        story.append(machine_table)
        story.append(Spacer(1, 4 * mm))

    # ── ITEMS TABLE ───────────────────────────────────────────────────────────
    items_header = Table(
        [[Paragraph("  ITENS DA ORDEM DE SERVIÇO", section_header_style)]],
        colWidths=[page_width],
        rowHeights=[7 * mm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_PRIMARY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]),
    )
    story.append(items_header)

    col_header_style = ParagraphStyle(
        "ColHeader",
        parent=styles["Normal"],
        fontSize=8,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    items_table_data = [
        [
            Paragraph("Tipo", col_header_style),
            Paragraph("Descrição", col_header_style),
            Paragraph("Qtd", col_header_style),
            Paragraph("Vlr Unit.", col_header_style),
            Paragraph("Total", col_header_style),
        ]
    ]

    _TYPE_LABELS = {"SERVICO": "Serviço", "PECA": "Peça", "DESLOCAMENTO": "Deslocamento"}

    items = order_data.get("items", [])
    for i, item in enumerate(items):
        row_bg = colors.white if i % 2 == 0 else COLOR_LIGHT_GRAY
        item_type_label = _TYPE_LABELS.get(item.get("item_type", ""), "Outro")
        qty = item.get("quantity", 0)
        unit_price = item.get("unit_price", 0)
        total_price = item.get("total_price", 0)

        items_table_data.append([
            Paragraph(item_type_label, ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, alignment=TA_CENTER)),
            Paragraph(str(item.get("description", "")), ParagraphStyle("cell", parent=styles["Normal"], fontSize=8)),
            Paragraph(f"{qty}", ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, alignment=TA_RIGHT)),
            Paragraph(f"R$ {_fmt_currency(unit_price)}", ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, alignment=TA_RIGHT)),
            Paragraph(f"R$ {_fmt_currency(total_price)}", ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, alignment=TA_RIGHT)),
        ])

    items_col_widths = [
        20 * mm,
        page_width - 80 * mm,
        20 * mm,
        25 * mm,
        25 * mm,
    ]

    items_style = [
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("GRID", (0, 1), (-1, -1), 0.5, colors.HexColor("#d5d8dc")),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    # Alternating row colors
    for idx in range(1, len(items_table_data)):
        if idx % 2 == 0:
            items_style.append(("BACKGROUND", (0, idx), (-1, idx), COLOR_LIGHT_GRAY))

    items_table = Table(
        items_table_data,
        colWidths=items_col_widths,
        style=TableStyle(items_style),
        repeatRows=1,
    )
    story.append(items_table)
    story.append(Spacer(1, 4 * mm))

    # ── FINANCIAL SUMMARY ─────────────────────────────────────────────────────
    def _to_decimal(v) -> Decimal:
        if v is None:
            return Decimal("0.00")
        try:
            return Decimal(str(v))
        except Exception:
            return Decimal("0.00")

    total_services = _to_decimal(order_data.get("total_services"))
    total_parts = _to_decimal(order_data.get("total_parts"))
    total_displacement = _to_decimal(order_data.get("total_displacement"))
    total_discount = _to_decimal(order_data.get("total_discount"))
    total_amount = _to_decimal(order_data.get("total_amount"))
    # Garante total correto mesmo se total_amount não foi calculado
    if total_amount == Decimal("0.00"):
        total_amount = total_services + total_parts + total_displacement - total_discount

    def _sumval(txt: str, color=None) -> Paragraph:
        style = ParagraphStyle(
            "sumval",
            parent=styles["Normal"],
            fontSize=9,
            alignment=TA_RIGHT,
            textColor=color or colors.black,
        )
        return Paragraph(txt, style)

    summary_data = [
        [
            Paragraph("Subtotal Serviços:", label_style),
            _sumval(f"R$ {_fmt_currency(total_services)}"),
        ],
        [
            Paragraph("Subtotal Peças:", label_style),
            _sumval(f"R$ {_fmt_currency(total_parts)}"),
        ],
    ]

    # Linha de deslocamento só aparece se houver valor
    if Decimal(str(total_displacement)) > 0:
        summary_data.append([
            Paragraph("Subtotal Deslocamento:", label_style),
            _sumval(f"R$ {_fmt_currency(total_displacement)}"),
        ])

    if total_discount > Decimal("0.00"):
        summary_data.append([
            Paragraph("Desconto:", label_style),
            _sumval(f"- R$ {_fmt_currency(total_discount)}", color=colors.HexColor("#c0392b")),
        ])

    summary_data += [
        [
            Paragraph("TOTAL:", ParagraphStyle("totallabel", parent=styles["Normal"], fontSize=12, fontName="Helvetica-Bold", textColor=COLOR_PRIMARY)),
            Paragraph(f"R$ {_fmt_currency(total_amount)}", ParagraphStyle("totalval", parent=styles["Normal"], fontSize=12, fontName="Helvetica-Bold", textColor=COLOR_PRIMARY, alignment=TA_RIGHT)),
        ],
    ]

    # Largura do bloco de resumo (lado direito): 130 mm
    _SUMMARY_WIDTH = 130 * mm
    _LABEL_W = 78 * mm
    _VALUE_W = 52 * mm  # _LABEL_W + _VALUE_W == _SUMMARY_WIDTH

    summary_table = Table(
        summary_data,
        colWidths=[_LABEL_W, _VALUE_W],
        style=TableStyle([
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("LINEABOVE", (0, -1), (-1, -1), 1.5, COLOR_PRIMARY),
            ("BACKGROUND", (0, -1), (-1, -1), COLOR_LIGHT_GRAY),
            ("TOPPADDING", (0, -1), (-1, -1), 7),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
        ]),
    )
    # Empurra o bloco para a direita (coluna esquerda vazia)
    outer_summary = Table(
        [[Paragraph(""), summary_table]],
        colWidths=[page_width - _SUMMARY_WIDTH, _SUMMARY_WIDTH],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]),
    )
    story.append(outer_summary)
    story.append(Spacer(1, 4 * mm))

    # ── PIX PAYMENT BLOCK (if configured) ────────────────────────────────────
    pix_key = order_data.get("pix_key")
    if pix_key and total_amount > 0:
        try:
            from app.modules.reports.pix_utils import build_pix_payload, build_pix_qrcode_png

            pix_payload = build_pix_payload(
                key=pix_key,
                beneficiary_name=order_data.get("tenant_name", "Oficina") or "Oficina",
                city=order_data.get("tenant_city", "BRASIL") or "BRASIL",
                amount=float(total_amount),
                description=f"OS#{order_data.get('os_number', '')}",
            )
            qr_png = build_pix_qrcode_png(pix_payload, box_size=4)
            qr_img = Image(io.BytesIO(qr_png), width=28 * mm, height=28 * mm)

            pix_header_style = ParagraphStyle(
                "pixheader",
                parent=styles["Normal"],
                fontSize=9,
                fontName="Helvetica-Bold",
                textColor=colors.HexColor("#1a6b3a"),
                alignment=TA_LEFT,
            )
            pix_key_style = ParagraphStyle(
                "pixkey",
                parent=styles["Normal"],
                fontSize=8,
                fontName="Helvetica",
                textColor=colors.black,
            )
            pix_small_style = ParagraphStyle(
                "pixsmall",
                parent=styles["Normal"],
                fontSize=7,
                fontName="Helvetica",
                textColor=COLOR_DARK_GRAY,
            )

            pix_key_type = order_data.get("pix_key_type") or "PIX"
            pix_info_rows = [
                [Paragraph("💚  PAGAMENTO VIA PIX", pix_header_style)],
                [Spacer(1, 2 * mm)],
                [Paragraph(f"<b>Tipo:</b> {pix_key_type}", pix_key_style)],
                [Paragraph(f"<b>Chave:</b> {pix_key}", pix_key_style)],
                [Spacer(1, 1 * mm)],
                [Paragraph(f"Valor: R$ {_fmt_currency(total_amount)}", pix_key_style)],
                [Spacer(1, 2 * mm)],
                [Paragraph("Escaneie o QR Code ou copie a chave para pagar.", pix_small_style)],
            ]

            pix_info_cell = Table(
                pix_info_rows,
                colWidths=[page_width - 38 * mm],
                style=TableStyle([
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]),
            )

            pix_block = Table(
                [[qr_img, pix_info_cell]],
                colWidths=[34 * mm, page_width - 34 * mm],
                style=TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0faf4")),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#27ae60")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (0, -1), 4),
                    ("RIGHTPADDING", (0, 0), (0, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]),
            )

            story.append(pix_block)
            story.append(Spacer(1, 6 * mm))
        except Exception:
            # Se falhar (qrcode não instalado, etc.) não interrompe o PDF
            story.append(Spacer(1, 4 * mm))
    else:
        story.append(Spacer(1, 4 * mm))

    # ── DIAGNOSIS & SOLUTION (if present) ────────────────────────────────────
    if order_data.get("diagnosis") or order_data.get("solution"):
        story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_DARK_GRAY))
        story.append(Spacer(1, 3 * mm))

        if order_data.get("diagnosis"):
            story.append(Paragraph("Diagnóstico:", label_style))
            story.append(Paragraph(str(order_data["diagnosis"]), value_style))
            story.append(Spacer(1, 3 * mm))

        if order_data.get("solution"):
            story.append(Paragraph("Solução Aplicada:", label_style))
            story.append(Paragraph(str(order_data["solution"]), value_style))
            story.append(Spacer(1, 3 * mm))

    # ── SIGNATURES ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 10 * mm))
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_DARK_GRAY))
    story.append(Spacer(1, 4 * mm))

    sig_line = "_" * 45
    sig_label_style = ParagraphStyle(
        "siglabel",
        parent=styles["Normal"],
        fontSize=8,
        textColor=COLOR_DARK_GRAY,
        alignment=TA_CENTER,
    )
    sig_meta_style = ParagraphStyle(
        "sigmeta",
        parent=styles["Normal"],
        fontSize=7,
        textColor=COLOR_DARK_GRAY,
        alignment=TA_CENTER,
    )

    half_w = page_width / 2

    # ── Célula do Técnico ─────────────────────────────────────────────────────
    sig_url = order_data.get("technician_signature_url")
    sig_img = _load_signature_image(sig_url, width=130, height=55)
    technician_name = str(order_data.get("technician_name") or "")

    if sig_img:
        tecnico_rows = [
            [sig_img],
            [Paragraph(technician_name, sig_meta_style)],
            [Paragraph("Técnico Responsável", sig_label_style)],
        ]
    else:
        tecnico_rows = [
            [Spacer(1, 14 * mm)],
            [Paragraph(sig_line, ParagraphStyle("sig", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER))],
            [Paragraph(technician_name, sig_meta_style)] if technician_name else [Paragraph("", sig_meta_style)],
            [Paragraph("Assinatura do Técnico", sig_label_style)],
        ]

    tecnico_cell = Table(
        tecnico_rows,
        colWidths=[half_w],
        style=TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]),
    )

    # ── Célula do Cliente ─────────────────────────────────────────────────────
    client_sig_b64 = order_data.get("budget_signature")        # base64 data URI
    client_sig_img = _load_signature_image(client_sig_b64, width=130, height=55)
    signer_name = str(order_data.get("budget_signer_name") or "")
    signer_doc = str(order_data.get("budget_signer_document") or "")
    approved_at = order_data.get("budget_approved_at")

    if client_sig_img:
        cliente_rows: list = [
            [client_sig_img],
        ]
        if signer_name:
            cliente_rows.append([Paragraph(signer_name, sig_meta_style)])
        if signer_doc:
            cliente_rows.append([Paragraph(f"Doc: {signer_doc}", sig_meta_style)])
        if approved_at:
            cliente_rows.append([Paragraph(f"Aprovado em {_fmt_datetime(approved_at)}", sig_meta_style)])
        cliente_rows.append([Paragraph("Assinatura do Cliente", sig_label_style)])
    else:
        # Sem assinatura digital: linha em branco para assinar fisicamente
        cliente_rows = [
            [Spacer(1, 14 * mm)],
            [Paragraph(sig_line, ParagraphStyle("sig", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER))],
            [Paragraph(signer_name, sig_meta_style)] if signer_name else [Paragraph("", sig_meta_style)],
            [Paragraph("Assinatura do Cliente", sig_label_style)],
        ]

    cliente_cell = Table(
        cliente_rows,
        colWidths=[half_w],
        style=TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]),
    )

    sig_table = Table(
        [[tecnico_cell, cliente_cell]],
        colWidths=[half_w, half_w],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("LINEBEFORE", (1, 0), (1, -1), 0.5, COLOR_LIGHT_GRAY),
        ]),
    )
    story.append(sig_table)
    story.append(Spacer(1, 6 * mm))

    # ── FOOTER ────────────────────────────────────────────────────────────────
    generated_at = order_data.get("generated_at") or datetime.now()
    footer_text = (
        f"Documento gerado em {_fmt_datetime(generated_at)} | "
        f"{tenant_name} | Powered by AutoMaster"
    )
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_LIGHT_GRAY))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(footer_text, footer_style))

    doc.build(story)
    return buffer.getvalue()
