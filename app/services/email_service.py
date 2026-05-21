"""
EmailService — envio de e-mails transacionais.

Em desenvolvimento (EMAIL_ENABLED=False): apenas loga o conteúdo.
Em produção (EMAIL_ENABLED=True): envia via SMTP com aiosmtplib.
"""
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Carrega templates do diretório app/templates/
_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_jinja = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _render(template_name: str, **ctx) -> str:
    return _jinja.get_template(template_name).render(**ctx)


async def _send(to: str, subject: str, html: str) -> None:
    if not settings.EMAIL_ENABLED:
        logger.info(
            "email_mock",
            to=to,
            subject=subject,
            preview=html[:200],
        )
        return

    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
    msg["To"] = to
    msg.attach(MIMEText(html, "html", "utf-8"))

    await aiosmtplib.send(
        msg,
        hostname=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        username=settings.EMAIL_USER,
        password=settings.EMAIL_PASS,
        start_tls=True,
    )
    logger.info("email_sent", to=to, subject=subject)


async def send_temp_password(
    to: str,
    full_name: str,
    senha_temp: str,
    tenant_id: str | None = None,
) -> None:
    """
    Envia email com senha temporária para novo usuário.
    Quando tenant_id é fornecido, o link de acesso já vem com o código da oficina
    preenchido automaticamente (sem necessidade de digitar).
    """
    if tenant_id:
        login_url = f"{settings.APP_URL}/login?tenant={tenant_id}"
    else:
        login_url = f"{settings.APP_URL}/login"

    html = _render(
        "temp_password.html",
        full_name=full_name,
        email=to,
        senha_temp=senha_temp,
        login_url=login_url,
        app_url=settings.APP_URL,
        app_name=settings.APP_NAME,
    )
    await _send(to, f"[{settings.APP_NAME}] Seu acesso foi criado", html)


async def send_reset_link(to: str, full_name: str, token: str) -> None:
    """Envia email com link para redefinir senha."""
    reset_url = f"{settings.APP_URL}/reset-password?token={token}"
    html = _render(
        "reset_password.html",
        full_name=full_name,
        reset_url=reset_url,
        expire_minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
        app_name=settings.APP_NAME,
    )
    await _send(to, f"[{settings.APP_NAME}] Redefinição de senha", html)
