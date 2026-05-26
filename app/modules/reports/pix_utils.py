"""
Utilitários PIX — gera payload EMV (Pix Copia e Cola) e QR Code.

Especificação: Banco Central do Brasil — Manual do BR Code (EMV QRCodeSpec).
"""
from __future__ import annotations

import io
import re
import unicodedata


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tlv(field_id: str, value: str) -> str:
    """Formata campo EMV: ID (2 chars) + comprimento (2 dígitos) + valor."""
    return f"{field_id}{len(value):02d}{value}"


def _crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE usado pelo PIX (polinômio 0x1021)."""
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


def _clean_key(key: str) -> str:
    """
    Remove formatação de CPF/CNPJ (pontos, traços, barras).
    Telefone: garante prefixo +55 e só dígitos após.
    E-mail e EVP: apenas strip.
    """
    key = key.strip()
    # CPF (000.000.000-00) ou CNPJ (00.000.000/0001-00) — só dígitos
    if re.match(r'^[\d.\-/]+$', key):
        digits = re.sub(r'\D', '', key)
        return digits
    # Telefone com formatação: (11) 99999-9999 → +5511999999999
    if re.match(r'^[\d()\s\-+]+$', key):
        digits = re.sub(r'\D', '', key)
        if len(digits) in (10, 11) and not key.startswith('+'):
            return f"+55{digits}"
        return key
    return key


def _ascii_name(name: str) -> str:
    """Remove acentos e caracteres não-ASCII para o campo 59 do EMV."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    # Mantém apenas caracteres permitidos pela spec (A-Z a-z 0-9 espaço . - _)
    clean = re.sub(r'[^A-Za-z0-9 .\-_]', '', ascii_str)
    return clean.strip()[:25] or "OFICINA"


# ── EMV payload ───────────────────────────────────────────────────────────────

def build_pix_payload(
    key: str,
    beneficiary_name: str,
    city: str,
    amount: float | None = None,
    description: str = "",
) -> str:
    """
    Gera o payload PIX estático no padrão EMV (Pix Copia e Cola).

    Args:
        key:               Chave PIX (CPF, CNPJ, email, telefone ou EVP)
        beneficiary_name:  Nome do beneficiário (máx. 25 chars, sem acentos)
        city:              Cidade do beneficiário (máx. 15 chars)
        amount:            Valor da transação (None = valor livre)
        description:       Ignorado no txid — usamos "***" (QR estático)

    Returns:
        String do payload pronta para gerar QR Code.
    """
    pix_key = _clean_key(key)
    name = _ascii_name(beneficiary_name)
    city_str = _ascii_name(city)[:15] or "BRASIL"

    # Merchant Account Information (campo 26) — sem campo 02 (descrição)
    # Campo 02 pode causar rejeição em alguns apps
    gui = _tlv("00", "BR.GOV.BCB.PIX")
    chave = _tlv("01", pix_key)
    merchant_info = _tlv("26", gui + chave)

    # Additional Data Field (campo 62.05) — txid obrigatório, sempre "***" em QR estático
    additional = _tlv("62", _tlv("05", "***"))

    # Formata o valor: sem separador de milhar, 2 casas decimais
    amount_str = ""
    if amount and amount > 0:
        amount_str = _tlv("54", f"{amount:.2f}")

    payload_no_crc = (
        _tlv("00", "01")    # Payload Format Indicator
        + merchant_info     # Merchant Account Info
        + _tlv("52", "0000")  # Merchant Category Code
        + _tlv("53", "986")   # Transaction Currency (BRL=986)
        + amount_str          # Transaction Amount (opcional)
        + _tlv("58", "BR")    # Country Code
        + _tlv("59", name)    # Merchant Name
        + _tlv("60", city_str)  # Merchant City
        + additional          # Additional Data (txid)
        + "6304"              # CRC placeholder
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
