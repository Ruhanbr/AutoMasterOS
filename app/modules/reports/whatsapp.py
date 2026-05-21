import urllib.parse


def build_whatsapp_link(phone: str, message: str) -> str:
    """
    Gera link wa.me para envio de mensagem ao cliente.
    phone: qualquer formato (55119..., +55119..., (11) 9...) → normaliza para dígitos
    """
    digits = "".join(c for c in phone if c.isdigit())
    # Adiciona DDI 55 se não tiver (número brasileiro)
    if not digits.startswith("55") and len(digits) <= 11:
        digits = "55" + digits
    encoded = urllib.parse.quote(message, safe="")
    return f"https://wa.me/{digits}?text={encoded}"


def build_os_whatsapp_message(
    client_name: str,
    os_number: int,
    total: str,
    workshop_name: str,
) -> str:
    return (
        f"Olá {client_name}! 🚜\n\n"
        f"Sua Ordem de Serviço *#{os_number}* da {workshop_name} foi finalizada.\n"
        f"*Valor total: R$ {total}*\n\n"
        f"Entre em contato para mais informações.\n"
        f"Agradecemos pela preferência! ✅"
    )
