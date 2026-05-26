"""
OS PDF generator using ReportLab — Modern redesign.

Layout:
  • Header band com logo, nome da oficina e número/status da OS
  • Faixa de metadados (abertura, técnico, finalização)
  • Cards lado a lado: Cliente | Máquina
  • Tabela de itens clean com zebra
  • Bloco de totais alinhado à direita
  • Bloco PIX (condicional) verde
  • Diagnóstico / Solução
  • Área de assinaturas
  • Footer
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
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Paleta ────────────────────────────────────────────────────────────────────
C_PRIMARY    = colors.HexColor("#1B3A5C")   # azul‑marinho profundo
C_ACCENT     = colors.HexColor("#2E7D32")   # verde agrícola
C_ACCENT_LT  = colors.HexColor("#E8F5E9")   # verde claro (fundo PIX)
C_ORANGE     = colors.HexColor("#E65100")   # despesas / peças
C_HEADER_BG  = colors.HexColor("#1B3A5C")   # fundo do cabeçalho
C_HEADER_SUB = colors.HexColor("#234870")   # fundo da faixa de metadados
C_ROW_ALT    = colors.HexColor("#F5F7FA")   # linha alternada da tabela
C_BORDER     = colors.HexColor("#D0D7DE")   # bordas suaves
C_GRAY       = colors.HexColor("#6E7781")   # texto secundário
C_DARK       = colors.HexColor("#1F2937")   # texto principal
C_WHITE      = colors.white
C_TOTAL_BG   = colors.HexColor("#EBF3FB")   # fundo do bloco de totais
C_STATUS = {
    "ABERTA":       colors.HexColor("#1565C0"),
    "EM_ANDAMENTO": colors.HexColor("#E65100"),
    "FINALIZADA":   colors.HexColor("#2E7D32"),
    "CANCELADA":    colors.HexColor("#B71C1C"),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _status_color(status: str) -> colors.Color:
    return C_STATUS.get(status, C_GRAY)


def _status_label(status: str) -> str:
    return {
        "ABERTA": "ABERTA",
        "EM_ANDAMENTO": "EM ANDAMENTO",
        "FINALIZADA": "FINALIZADA",
        "CANCELADA": "CANCELADA",
    }.get(status, status)


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


def _load_image(url: str | None, width: int = 120, height: int = 50) -> Image | None:
    if not url:
        return None
    try:
        import base64, os, urllib.request
        if url.startswith("data:"):
            header, encoded = url.split(",", 1)
            source = io.BytesIO(base64.b64decode(encoded))
        elif url.startswith(("http://", "https://")):
            tmp = f"/tmp/sig_{abs(hash(url))}.img"
            if not os.path.exists(tmp):
                urllib.request.urlretrieve(url, tmp)
            source = tmp
        else:
            if not os.path.exists(url):
                return None
            source = url
        return Image(source, width=width, height=height, kind="proportional")
    except Exception:
        return None


def _section_header(text: str, page_width: float, bg=None) -> Table:
    """Faixa colorida de seção com texto em maiúsculas."""
    bg = bg or C_PRIMARY
    style = ParagraphStyle(
        "sh", fontSize=8, fontName="Helvetica-Bold",
        textColor=C_WHITE, alignment=TA_LEFT,
    )
    t = Table([[Paragraph(f"  {text}", style)]], colWidths=[page_width], rowHeights=[6.5 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _label_value(label: str, value: str,
                 label_style: ParagraphStyle,
                 value_style: ParagraphStyle) -> list:
    return [Paragraph(label, label_style), Paragraph(value or "—", value_style)]


# ── Main generator ────────────────────────────────────────────────────────────

def generate_os_pdf(order_data: dict) -> bytes:
    """
    Gera o PDF de OS com layout moderno.
    Todos os campos de order_data são os mesmos da versão anterior.
    """
    buffer = io.BytesIO()
    page_w = A4[0] - 24 * mm   # largura útil

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=12 * mm, leftMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"OS #{order_data.get('os_number', '')}",
        author=order_data.get("tenant_name", "AutoMaster"),
    )

    styles = getSampleStyleSheet()

    # ── Estilos reutilizáveis ─────────────────────────────────────────────────
    def S(name, **kw):
        base = kw.pop("parent", styles["Normal"])
        return ParagraphStyle(name, parent=base, **kw)

    lbl = S("lbl", fontSize=7, fontName="Helvetica-Bold", textColor=C_GRAY)
    val = S("val", fontSize=8.5, fontName="Helvetica", textColor=C_DARK)
    val_mono = S("vmono", fontSize=8, fontName="Helvetica", textColor=C_DARK)
    footer_s = S("foot", fontSize=6.5, fontName="Helvetica", textColor=C_GRAY, alignment=TA_CENTER)
    total_lbl = S("tlbl", fontSize=9,  fontName="Helvetica-Bold", textColor=C_GRAY)
    total_val = S("tval", fontSize=9,  fontName="Helvetica", textColor=C_DARK, alignment=TA_RIGHT)
    grand_lbl = S("glbl", fontSize=12, fontName="Helvetica-Bold", textColor=C_PRIMARY)
    grand_val = S("gval", fontSize=12, fontName="Helvetica-Bold", textColor=C_PRIMARY, alignment=TA_RIGHT)
    col_hdr_s = S("ch", fontSize=8, fontName="Helvetica-Bold", textColor=C_WHITE, alignment=TA_CENTER)
    cell_s    = S("cs", fontSize=8, fontName="Helvetica", textColor=C_DARK)
    cell_r    = S("cr", fontSize=8, fontName="Helvetica", textColor=C_DARK, alignment=TA_RIGHT)
    cell_c    = S("cc", fontSize=8, fontName="Helvetica", textColor=C_DARK, alignment=TA_CENTER)
    sig_lbl_s = S("sl", fontSize=7.5, fontName="Helvetica", textColor=C_GRAY, alignment=TA_CENTER)
    sig_name_s= S("sn", fontSize=8,   fontName="Helvetica-Bold", textColor=C_DARK, alignment=TA_CENTER)
    pix_hdr_s = S("ph", fontSize=9,   fontName="Helvetica-Bold", textColor=C_ACCENT)
    pix_val_s = S("pv", fontSize=8,   fontName="Helvetica", textColor=C_DARK)
    pix_sm_s  = S("ps", fontSize=7,   fontName="Helvetica", textColor=C_GRAY)
    meta_s    = S("ms", fontSize=8,   fontName="Helvetica", textColor=C_WHITE)
    meta_lbl_s= S("ml", fontSize=7,   fontName="Helvetica-Bold", textColor=colors.HexColor("#A8C4E0"))
    diag_s    = S("ds", fontSize=8.5, fontName="Helvetica", textColor=C_DARK, leading=13)

    story = []

    # ════════════════════════════════════════════════════════════════════════
    # 1. CABEÇALHO — banda azul com logo + info oficina + OS número / status
    # ════════════════════════════════════════════════════════════════════════
    tenant_name  = order_data.get("tenant_name", "AutoMaster Oficina")
    tenant_doc   = order_data.get("tenant_document", "")
    tenant_phone = order_data.get("tenant_phone", "")
    tenant_email = order_data.get("tenant_email", "")
    tenant_addr  = order_data.get("tenant_address", "")
    os_number    = order_data.get("os_number", "")
    status       = str(order_data.get("status", ""))
    status_color = _status_color(status)
    status_label = _status_label(status)

    # Logo
    logo_img = _load_image(order_data.get("tenant_logo_url"))
    if logo_img:
        logo_img.drawWidth  = 18 * mm
        logo_img.drawHeight = 18 * mm
        logo_img.kind = "proportional"
        logo_cell = logo_img
    else:
        # Quadrado colorido como placeholder
        logo_cell = Table([[""]], colWidths=[18*mm], rowHeights=[18*mm],
                          style=TableStyle([("BACKGROUND",(0,0),(-1,-1), colors.HexColor("#234870"))]))

    # Info da oficina (coluna central)
    oficina_name_s = S("on", fontSize=13, fontName="Helvetica-Bold", textColor=C_WHITE)
    oficina_sub_s  = S("os2", fontSize=8, fontName="Helvetica", textColor=colors.HexColor("#A8C4E0"))

    info_lines: list[Paragraph] = [Paragraph(tenant_name, oficina_name_s)]
    sub_parts = []
    if tenant_doc:
        label = "CPF" if len("".join(c for c in tenant_doc if c.isdigit())) == 11 else "CNPJ"
        sub_parts.append(f"{label}: {tenant_doc}")
    if tenant_phone:
        sub_parts.append(f"Tel: {tenant_phone}")
    if tenant_email:
        sub_parts.append(tenant_email)
    if sub_parts:
        info_lines.append(Paragraph("   ·   ".join(sub_parts), oficina_sub_s))
    if tenant_addr:
        info_lines.append(Paragraph(tenant_addr, oficina_sub_s))

    # Coluna direita: OS número + badge de status
    os_num_s  = S("osn", fontSize=22, fontName="Helvetica-Bold", textColor=C_WHITE, alignment=TA_RIGHT)
    os_type_s = S("ost", fontSize=8,  fontName="Helvetica", textColor=colors.HexColor("#A8C4E0"), alignment=TA_RIGHT)
    os_info_cell = [
        Paragraph("ORDEM DE SERVIÇO", os_type_s),
        Paragraph(f"#{os_number}", os_num_s),
    ]

    header_data = [[logo_cell, info_lines, os_info_cell]]
    header_table = Table(
        header_data,
        colWidths=[22*mm, page_w - 22*mm - 45*mm, 45*mm],
        style=TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), C_HEADER_BG),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING",   (0,0), (-1,-1), 5),
            ("RIGHTPADDING",  (0,0), (-1,-1), 5),
            ("TOPPADDING",    (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ]),
    )
    story.append(header_table)

    # Badge de status (faixa fina abaixo do cabeçalho)
    status_s = S("stbadge", fontSize=8.5, fontName="Helvetica-Bold", textColor=C_WHITE, alignment=TA_CENTER)
    status_table = Table(
        [[Paragraph(f"◉  {status_label}", status_s)]],
        colWidths=[page_w], rowHeights=[6*mm],
        style=TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), status_color),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0), (-1,-1), 0),
            ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ]),
    )
    story.append(status_table)

    # ════════════════════════════════════════════════════════════════════════
    # 2. FAIXA DE METADADOS — abertura | início | finalização | técnico
    # ════════════════════════════════════════════════════════════════════════
    meta_items = [
        ("Abertura",    _fmt_datetime(order_data.get("opened_at"))),
        ("Início",      _fmt_datetime(order_data.get("started_at") or order_data.get("opened_at"))),
        ("Finalização", _fmt_datetime(order_data.get("finished_at"))),
        ("Técnico",     str(order_data.get("technician_name") or "—")),
    ]
    meta_cells = []
    for mlabel, mval in meta_items:
        meta_cells.append([
            Paragraph(mlabel.upper(), meta_lbl_s),
            Paragraph(mval, meta_s),
        ])

    meta_col_w = page_w / len(meta_items)
    meta_data  = [
        [Table(mc, colWidths=[meta_col_w], style=TableStyle([
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
            ("RIGHTPADDING",  (0,0),(-1,-1), 4),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ])) for mc in meta_cells]
    ]
    meta_table = Table(meta_data, colWidths=[meta_col_w]*len(meta_items),
        style=TableStyle([
            ("BACKGROUND",  (0,0),(-1,-1), C_HEADER_SUB),
            ("VALIGN",      (0,0),(-1,-1), "TOP"),
            ("LINEAFTER",   (0,0),(-2,-1), 0.5, colors.HexColor("#2D5F8A")),
            ("TOPPADDING",    (0,0),(-1,-1), 0),
            ("BOTTOMPADDING", (0,0),(-1,-1), 0),
            ("LEFTPADDING",   (0,0),(-1,-1), 0),
            ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ]))
    story.append(meta_table)
    story.append(Spacer(1, 4*mm))

    # ════════════════════════════════════════════════════════════════════════
    # 3. DESCRIÇÃO DA OS (se houver)
    # ════════════════════════════════════════════════════════════════════════
    if order_data.get("description"):
        story.append(_section_header("DESCRIÇÃO DO SERVIÇO", page_w))
        desc_table = Table(
            [[Paragraph(str(order_data["description"]), diag_s)]],
            colWidths=[page_w],
            style=TableStyle([
                ("BACKGROUND",    (0,0),(-1,-1), C_ROW_ALT),
                ("LEFTPADDING",   (0,0),(-1,-1), 8),
                ("RIGHTPADDING",  (0,0),(-1,-1), 8),
                ("TOPPADDING",    (0,0),(-1,-1), 6),
                ("BOTTOMPADDING", (0,0),(-1,-1), 6),
                ("BOX",           (0,0),(-1,-1), 0.5, C_BORDER),
            ]),
        )
        story.append(desc_table)
        story.append(Spacer(1, 4*mm))

    # ════════════════════════════════════════════════════════════════════════
    # 4. CARDS LADO A LADO: CLIENTE | MÁQUINA
    # ════════════════════════════════════════════════════════════════════════
    client  = order_data
    machine = order_data
    half_w  = (page_w - 3*mm) / 2

    def _info_rows(pairs: list[tuple[str,str]]) -> list:
        rows = []
        for lbl_txt, val_txt in pairs:
            if val_txt and val_txt != "—":
                rows.append([Paragraph(lbl_txt, lbl), Paragraph(str(val_txt), val)])
        return rows or [[Paragraph("—", val), Paragraph("", val)]]

    # Cliente
    client_phone = str(order_data.get("client_phone") or "—")
    client_phone2 = order_data.get("client_phone_secondary")
    client_pairs = [
        ("Nome",             order_data.get("client_name")),
        ("CPF/CNPJ",         order_data.get("client_document")),
        ("Telefone",         client_phone),
        ("Tel. Secundário",  str(client_phone2) if client_phone2 else None),
        ("Fazenda",          order_data.get("client_fazenda")),
        ("Endereço",         order_data.get("client_address")),
        ("Insc. Estadual",   order_data.get("client_inscricao_estadual")),
    ]
    client_rows = _info_rows([(l,v) for l,v in client_pairs if v])

    client_card = Table(
        client_rows,
        colWidths=[28*mm, half_w - 28*mm],
        style=TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), colors.white),
            ("TOPPADDING",    (0,0),(-1,-1), 3),
            ("BOTTOMPADDING", (0,0),(-1,-1), 3),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("RIGHTPADDING",  (0,0),(-1,-1), 6),
            ("LINEBELOW",     (0,0),(-1,-2), 0.3, C_BORDER),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ]),
    )

    # Máquina
    machine_pairs = [
        ("Marca",        order_data.get("machine_brand")),
        ("Modelo",       order_data.get("machine_model")),
        ("Nº de Série",  order_data.get("machine_serial")),
        ("Ano",          str(order_data.get("machine_year")) if order_data.get("machine_year") else None),
        ("Chassi",       order_data.get("machine_chassis")),
        ("Placa",        order_data.get("machine_placa")),
        ("Proprietário", order_data.get("machine_proprietario")),
        ("Nº Motor",     order_data.get("machine_engine_number")),
        ("Potência",     order_data.get("machine_horsepower")),
    ]
    machine_rows = _info_rows([(l,v) for l,v in machine_pairs if v])

    machine_card = Table(
        machine_rows,
        colWidths=[28*mm, half_w - 28*mm],
        style=TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), colors.white),
            ("TOPPADDING",    (0,0),(-1,-1), 3),
            ("BOTTOMPADDING", (0,0),(-1,-1), 3),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("RIGHTPADDING",  (0,0),(-1,-1), 6),
            ("LINEBELOW",     (0,0),(-1,-2), 0.3, C_BORDER),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ]),
    )

    def _card_wrap(title: str, inner: Table, width: float) -> Table:
        title_s = S("ct", fontSize=8, fontName="Helvetica-Bold", textColor=C_WHITE)
        hdr = Table([[Paragraph(f"  {title}", title_s)]], colWidths=[width], rowHeights=[6*mm],
                    style=TableStyle([
                        ("BACKGROUND",    (0,0),(-1,-1), C_ACCENT),
                        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
                        ("TOPPADDING",    (0,0),(-1,-1), 0),
                        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
                    ]))
        outer = Table(
            [[hdr], [inner]],
            colWidths=[width],
            style=TableStyle([
                ("BOX",        (0,0),(-1,-1), 0.5, C_BORDER),
                ("TOPPADDING",    (0,0),(-1,-1), 0),
                ("BOTTOMPADDING", (0,0),(-1,-1), 0),
                ("LEFTPADDING",   (0,0),(-1,-1), 0),
                ("RIGHTPADDING",  (0,0),(-1,-1), 0),
            ]),
        )
        return outer

    client_wrapped  = _card_wrap("CLIENTE",             client_card,  half_w)
    machine_wrapped = _card_wrap("MÁQUINA / EQUIPAMENTO", machine_card, half_w)

    has_machine = order_data.get("machine_model") or order_data.get("machine_brand")
    if has_machine:
        cards_table = Table(
            [[client_wrapped, Spacer(3*mm, 1), machine_wrapped]],
            colWidths=[half_w, 3*mm, half_w],
            style=TableStyle([
                ("VALIGN",        (0,0),(-1,-1), "TOP"),
                ("TOPPADDING",    (0,0),(-1,-1), 0),
                ("BOTTOMPADDING", (0,0),(-1,-1), 0),
                ("LEFTPADDING",   (0,0),(-1,-1), 0),
                ("RIGHTPADDING",  (0,0),(-1,-1), 0),
            ]),
        )
    else:
        cards_table = Table(
            [[client_wrapped]],
            colWidths=[page_w],
            style=TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
                              ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),
                              ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]),
        )

    story.append(cards_table)
    story.append(Spacer(1, 4*mm))

    # ════════════════════════════════════════════════════════════════════════
    # 5. TABELA DE ITENS
    # ════════════════════════════════════════════════════════════════════════
    story.append(_section_header("ITENS DA ORDEM DE SERVIÇO", page_w))

    _TYPE_LABELS = {"SERVICO": "Serviço", "PECA": "Peça", "DESLOCAMENTO": "Deslocamento"}
    _TYPE_COLORS = {
        "SERVICO":      colors.HexColor("#1565C0"),
        "PECA":         colors.HexColor("#E65100"),
        "DESLOCAMENTO": colors.HexColor("#6A1B9A"),
    }

    col_tipo_w  = 28*mm
    col_desc_w  = page_w - 28*mm - 18*mm - 26*mm - 26*mm
    col_qty_w   = 18*mm
    col_unit_w  = 26*mm
    col_total_w = 26*mm

    items_data = [[
        Paragraph("TIPO",       col_hdr_s),
        Paragraph("DESCRIÇÃO",  col_hdr_s),
        Paragraph("QTD",        S("chr", fontSize=8, fontName="Helvetica-Bold", textColor=C_WHITE, alignment=TA_RIGHT)),
        Paragraph("UNIT.",      S("chr", fontSize=8, fontName="Helvetica-Bold", textColor=C_WHITE, alignment=TA_RIGHT)),
        Paragraph("TOTAL",      S("chr", fontSize=8, fontName="Helvetica-Bold", textColor=C_WHITE, alignment=TA_RIGHT)),
    ]]

    for item in order_data.get("items", []):
        itype = str(item.get("item_type", ""))
        type_color = _TYPE_COLORS.get(itype, C_GRAY)
        type_label = _TYPE_LABELS.get(itype, itype)
        qty   = float(item.get("quantity", 0))
        unit  = item.get("unit_price", 0)
        total = item.get("total_price", 0)

        type_s = S(f"it_{itype}", fontSize=7.5, fontName="Helvetica-Bold", textColor=type_color, alignment=TA_CENTER)

        items_data.append([
            Paragraph(type_label, type_s),
            Paragraph(str(item.get("description", "")), cell_s),
            Paragraph(f"{qty:.2f}", cell_r),
            Paragraph(f"R$ {_fmt_currency(unit)}",  cell_r),
            Paragraph(f"R$ {_fmt_currency(total)}", cell_r),
        ])

    items_style = TableStyle([
        # Cabeçalho
        ("BACKGROUND",    (0,0),(-1,0),  C_PRIMARY),
        ("TEXTCOLOR",     (0,0),(-1,0),  C_WHITE),
        ("TOPPADDING",    (0,0),(-1,0),  5),
        ("BOTTOMPADDING", (0,0),(-1,0),  5),
        # Linhas de dados
        ("FONTSIZE",      (0,1),(-1,-1), 8),
        ("TOPPADDING",    (0,1),(-1,-1), 4),
        ("BOTTOMPADDING", (0,1),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("RIGHTPADDING",  (0,0),(-1,-1), 6),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        # Linhas separadoras
        ("LINEBELOW",     (0,0),(-1,-1), 0.3, C_BORDER),
        ("BOX",           (0,0),(-1,-1), 0.5, C_BORDER),
    ])
    # Zebra nas linhas ímpares
    for i in range(1, len(items_data)):
        if i % 2 == 0:
            items_style.add("BACKGROUND", (0,i), (-1,i), C_ROW_ALT)

    items_table = Table(
        items_data,
        colWidths=[col_tipo_w, col_desc_w, col_qty_w, col_unit_w, col_total_w],
        style=items_style,
        repeatRows=1,
    )
    story.append(items_table)
    story.append(Spacer(1, 4*mm))

    # ════════════════════════════════════════════════════════════════════════
    # 6. BLOCO DE TOTAIS
    # ════════════════════════════════════════════════════════════════════════
    def _to_d(v) -> Decimal:
        try:
            return Decimal(str(v)) if v is not None else Decimal("0")
        except Exception:
            return Decimal("0")

    total_services    = _to_d(order_data.get("total_services"))
    total_parts       = _to_d(order_data.get("total_parts"))
    total_displacement= _to_d(order_data.get("total_displacement"))
    total_discount    = _to_d(order_data.get("total_discount"))
    total_amount      = _to_d(order_data.get("total_amount"))
    if total_amount == Decimal("0"):
        total_amount = total_services + total_parts + total_displacement - total_discount

    SUMMARY_W  = 120*mm
    LABEL_W    = 72*mm
    VALUE_W    = SUMMARY_W - LABEL_W

    summary_rows = [
        [Paragraph("Subtotal Serviços:",    total_lbl), Paragraph(f"R$ {_fmt_currency(total_services)}",     total_val)],
        [Paragraph("Subtotal Peças:",       total_lbl), Paragraph(f"R$ {_fmt_currency(total_parts)}",        total_val)],
    ]
    if total_displacement > 0:
        summary_rows.append(
            [Paragraph("Subtotal Deslocamento:", total_lbl), Paragraph(f"R$ {_fmt_currency(total_displacement)}", total_val)]
        )
    if total_discount > 0:
        disc_val_s = S("dv", fontSize=9, fontName="Helvetica", textColor=C_ORANGE, alignment=TA_RIGHT)
        summary_rows.append(
            [Paragraph("Desconto:", total_lbl), Paragraph(f"- R$ {_fmt_currency(total_discount)}", disc_val_s)]
        )
    summary_rows.append(
        [Paragraph("TOTAL GERAL:", grand_lbl), Paragraph(f"R$ {_fmt_currency(total_amount)}", grand_val)]
    )

    summary_inner = Table(
        summary_rows, colWidths=[LABEL_W, VALUE_W],
        style=TableStyle([
            ("BACKGROUND",    (0,0),(-1,-2), colors.white),
            ("BACKGROUND",    (0,-1),(-1,-1), C_TOTAL_BG),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
            ("RIGHTPADDING",  (0,0),(-1,-1), 8),
            ("LINEABOVE",     (0,-1),(-1,-1), 1.5, C_PRIMARY),
            ("LINEBELOW",     (0,0),(-1,-2), 0.3, C_BORDER),
            ("TOPPADDING",    (0,-1),(-1,-1), 7),
            ("BOTTOMPADDING", (0,-1),(-1,-1), 7),
            ("BOX",           (0,0),(-1,-1), 0.5, C_BORDER),
        ]),
    )

    outer_summary = Table(
        [[Paragraph("", val), summary_inner]],
        colWidths=[page_w - SUMMARY_W, SUMMARY_W],
        style=TableStyle([
            ("VALIGN",        (0,0),(-1,-1), "TOP"),
            ("TOPPADDING",    (0,0),(-1,-1), 0),
            ("BOTTOMPADDING", (0,0),(-1,-1), 0),
            ("LEFTPADDING",   (0,0),(-1,-1), 0),
            ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ]),
    )
    story.append(outer_summary)
    story.append(Spacer(1, 5*mm))

    # ════════════════════════════════════════════════════════════════════════
    # 7. BLOCO PIX (condicional)
    # ════════════════════════════════════════════════════════════════════════
    pix_key = order_data.get("pix_key")
    if pix_key and total_amount > 0:
        try:
            from app.modules.reports.pix_utils import build_pix_payload, build_pix_qrcode_png
            pix_payload = build_pix_payload(
                key=pix_key,
                beneficiary_name=order_data.get("tenant_name", "Oficina") or "Oficina",
                city=order_data.get("tenant_city", "BRASIL") or "BRASIL",
                amount=float(total_amount),
                description=f"OS{order_data.get('os_number', '')}",
            )
            qr_png = build_pix_qrcode_png(pix_payload, box_size=4)
            qr_img = Image(io.BytesIO(qr_png), width=28*mm, height=28*mm)

            pix_key_type = order_data.get("pix_key_type") or "PIX"
            pix_info_rows = [
                [Paragraph("PAGAMENTO VIA PIX", pix_hdr_s)],
                [Spacer(1, 1.5*mm)],
                [Paragraph(f"<b>Tipo:</b> {pix_key_type}   <b>Chave:</b> {pix_key}", pix_val_s)],
                [Paragraph(f"<b>Valor:</b> R$ {_fmt_currency(total_amount)}", pix_val_s)],
                [Spacer(1, 1.5*mm)],
                [Paragraph("Escaneie o QR Code ou copie a chave no app do banco.", pix_sm_s)],
            ]
            pix_info_cell = Table(pix_info_rows, colWidths=[page_w - 38*mm],
                style=TableStyle([
                    ("LEFTPADDING",   (0,0),(-1,-1), 6),
                    ("TOPPADDING",    (0,0),(-1,-1), 1),
                    ("BOTTOMPADDING", (0,0),(-1,-1), 1),
                ]))

            pix_block = Table(
                [[qr_img, pix_info_cell]],
                colWidths=[34*mm, page_w - 34*mm],
                style=TableStyle([
                    ("BACKGROUND",    (0,0),(-1,-1), C_ACCENT_LT),
                    ("BOX",           (0,0),(-1,-1), 1, C_ACCENT),
                    ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
                    ("LEFTPADDING",   (0,0),(0,-1),  4),
                    ("TOPPADDING",    (0,0),(-1,-1), 6),
                    ("BOTTOMPADDING", (0,0),(-1,-1), 6),
                ]),
            )
            story.append(pix_block)
            story.append(Spacer(1, 5*mm))
        except Exception:
            story.append(Spacer(1, 2*mm))

    # ════════════════════════════════════════════════════════════════════════
    # 8. DIAGNÓSTICO & SOLUÇÃO
    # ════════════════════════════════════════════════════════════════════════
    if order_data.get("diagnosis") or order_data.get("solution"):
        story.append(_section_header("DIAGNÓSTICO E SOLUÇÃO", page_w))
        ds_rows = []
        if order_data.get("diagnosis"):
            ds_rows.append([Paragraph("Diagnóstico:", lbl), Paragraph(str(order_data["diagnosis"]), diag_s)])
        if order_data.get("solution"):
            ds_rows.append([Paragraph("Solução:",     lbl), Paragraph(str(order_data["solution"]),  diag_s)])

        ds_table = Table(ds_rows, colWidths=[24*mm, page_w - 24*mm],
            style=TableStyle([
                ("BACKGROUND",    (0,0),(-1,-1), C_ROW_ALT),
                ("TOPPADDING",    (0,0),(-1,-1), 5),
                ("BOTTOMPADDING", (0,0),(-1,-1), 5),
                ("LEFTPADDING",   (0,0),(-1,-1), 8),
                ("RIGHTPADDING",  (0,0),(-1,-1), 8),
                ("LINEBELOW",     (0,0),(-1,-2), 0.3, C_BORDER),
                ("BOX",           (0,0),(-1,-1), 0.5, C_BORDER),
                ("VALIGN",        (0,0),(-1,-1), "TOP"),
            ]))
        story.append(ds_table)
        story.append(Spacer(1, 5*mm))

    # ════════════════════════════════════════════════════════════════════════
    # 9. ÁREA DE ASSINATURAS
    # ════════════════════════════════════════════════════════════════════════
    story.append(HRFlowable(width=page_w, thickness=0.5, color=C_BORDER))
    story.append(Spacer(1, 5*mm))

    half_sig = page_w / 2

    # Técnico
    sig_url = order_data.get("technician_signature_url")
    sig_img = _load_image(sig_url, width=130, height=55)
    tech_name = str(order_data.get("technician_name") or "")

    if sig_img:
        tech_rows: list = [[sig_img]]
    else:
        tech_rows = [
            [Spacer(1, 14*mm)],
            [HRFlowable(width=half_sig - 20*mm, thickness=0.8, color=C_GRAY)],
        ]
    if tech_name:
        tech_rows.append([Paragraph(tech_name, sig_name_s)])
    tech_rows.append([Paragraph("Técnico Responsável", sig_lbl_s)])

    tech_cell = Table(tech_rows, colWidths=[half_sig],
        style=TableStyle([
            ("ALIGN",         (0,0),(-1,-1), "CENTER"),
            ("VALIGN",        (0,0),(-1,-1), "BOTTOM"),
            ("TOPPADDING",    (0,0),(-1,-1), 2),
            ("BOTTOMPADDING", (0,0),(-1,-1), 2),
        ]))

    # Cliente
    client_sig_b64 = order_data.get("budget_signature")
    client_sig_img = _load_image(client_sig_b64, width=130, height=55)
    signer_name = str(order_data.get("budget_signer_name") or "")
    signer_doc  = str(order_data.get("budget_signer_document") or "")
    approved_at = order_data.get("budget_approved_at")

    if client_sig_img:
        client_rows: list = [[client_sig_img]]
        if signer_name:
            client_rows.append([Paragraph(signer_name, sig_name_s)])
        if signer_doc:
            client_rows.append([Paragraph(f"Doc: {signer_doc}", sig_lbl_s)])
        if approved_at:
            client_rows.append([Paragraph(f"Aprovado em {_fmt_datetime(approved_at)}", sig_lbl_s)])
        client_rows.append([Paragraph("Assinatura do Cliente", sig_lbl_s)])
    else:
        client_rows = [
            [Spacer(1, 14*mm)],
            [HRFlowable(width=half_sig - 20*mm, thickness=0.8, color=C_GRAY)],
            [Paragraph(signer_name, sig_name_s)] if signer_name else [Spacer(1, 1*mm)],
            [Paragraph("Assinatura do Cliente", sig_lbl_s)],
        ]

    client_cell = Table(client_rows, colWidths=[half_sig],
        style=TableStyle([
            ("ALIGN",         (0,0),(-1,-1), "CENTER"),
            ("VALIGN",        (0,0),(-1,-1), "BOTTOM"),
            ("TOPPADDING",    (0,0),(-1,-1), 2),
            ("BOTTOMPADDING", (0,0),(-1,-1), 2),
        ]))

    sig_table = Table(
        [[tech_cell, client_cell]], colWidths=[half_sig, half_sig],
        style=TableStyle([
            ("VALIGN",      (0,0),(-1,-1), "BOTTOM"),
            ("LINEBEFORE",  (1,0),(1,-1),  0.5, C_BORDER),
            ("LEFTPADDING", (0,0),(-1,-1), 0),
            ("RIGHTPADDING",(0,0),(-1,-1), 0),
            ("TOPPADDING",  (0,0),(-1,-1), 0),
            ("BOTTOMPADDING",(0,0),(-1,-1), 0),
        ]))
    story.append(sig_table)
    story.append(Spacer(1, 5*mm))

    # ════════════════════════════════════════════════════════════════════════
    # 10. FOOTER
    # ════════════════════════════════════════════════════════════════════════
    generated_at = order_data.get("generated_at") or datetime.now()
    footer_text = (
        f"Documento gerado em {_fmt_datetime(generated_at)}  ·  "
        f"{tenant_name}  ·  Powered by AutoMaster"
    )
    story.append(HRFlowable(width=page_w, thickness=0.3, color=C_BORDER))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(footer_text, footer_s))

    doc.build(story)
    return buffer.getvalue()
