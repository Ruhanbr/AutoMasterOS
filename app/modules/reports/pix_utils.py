"""
Utilitários PIX — gera payload EMV (Pix Copia e Cola) e QR Code.

Especificação: Banco Central do Brasil — Manual do BR Code (EMV QRCodeSpec).
"""
from __future__ import annotations

import io


# ── EMV payload ───────────────────────────────────────────────────────────────

def _tlv(field_id: str, value: str) -> str:
    """Formata campo EMV: ID (2 chars) + comprimento (2 dígitos) + valor."""
    return f"{field_id}{len(value):02d}{value}"


def _crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE usado pelo PIX."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def build_pix_payload(
    key: str,
    beneficiary_name: str,
    city: str,
    amount: float | None = None,
    description: str = "",
) -> str:
    """
    Gera o payload PIX no padrão EMV (Pix Copia e Cola).

    Args:
        key:               Chave PIX (CPF, CNPJ, email, telefone ou EVP)
        beneficiary_name:  Nome do beneficiário (máx. 25 chars)
        city:              Cidade do beneficiário (máx. 15 chars)
        amount:            Valor da transação (None = valor livre)
        description:       Descrição opcional (txid / referência)

    Returns:
        String do payload pronta para gerar QR Code.
    """
    key = key.strip()
    name = beneficiary_name[:25].strip()
    city_str = city[:15].strip() if city else "BRASIL"
    txid = (description or "***")[:25]

    # Merchant Account Information (campo 26)
    gui = _tlv("00", "BR.GOV.BCB.PIX")
    chave = _tlv("01", key)
    if description:
        info_adicional = _tlv("02", description[:72])
        merchant_info = _tlv("26", gui + chave + info_adicional)
    else:
        merchant_info = _tlv("26", gui + chave)

    # Additional Data Field (campo 62) — txid
    additional = _tlv("62", _tlv("05", txid))

    payload_no_crc = (
        _tlv("00", "01")           # Payload Format Indicator
        + merchant_info            # Merchant Account Info
        + _tlv("52", "0000")       # Merchant Category Code
        + _tlv("53", "986")        # Transaction Currency (BRL)
        + (_tlv("54", f"{amount:.2f}") if amount and amount > 0 else "")
        + _tlv("58", "BR")         # Country Code
        + _tlv("59", name)         # Merchant Name
        + _tlv("60", city_str)     # Merchant City
        + additional               # Additional Data
        + "6304"                   # CRC placeholder (preenchido abaixo)
    )

    crc = _crc16(payload_no_crc.encode("utf-8"))
    return payload_no_crc + f"{crc:04X}"


# ── QR Code → bytes PNG ───────────────────────────────────────────────────────

def build_pix_qrcode_png(payload: str, box_size: int = 4) -> bytes:
    """
    Gera um QR Code PIX e retorna como PNG em bytes.

    Requires: qrcode[pil]
    """
    import qrcode  # type: ignore[import-untyped]

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()
