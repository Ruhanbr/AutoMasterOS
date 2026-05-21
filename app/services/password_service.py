"""
PasswordService — geração de senhas temporárias e tokens de reset.
"""
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.password_reset_token import PasswordResetToken


class PasswordService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Senha temporária ──────────────────────────────────────────────────────

    @staticmethod
    def gerar_senha_temporaria(length: int = 12) -> str:
        """Gera senha temporária segura com letras, números e símbolos."""
        alphabet = string.ascii_letters + string.digits + "!@#$%"
        # Garante ao menos 1 de cada categoria
        password = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.digits),
            secrets.choice("!@#$%"),
        ]
        password += [secrets.choice(alphabet) for _ in range(length - 4)]
        secrets.SystemRandom().shuffle(password)
        return "".join(password)

    # ── Token de reset ────────────────────────────────────────────────────────

    async def criar_token_reset(self, user_id: uuid.UUID) -> str:
        """
        Invalida tokens anteriores do usuário e cria um novo.
        Retorna o token em texto claro (enviado por email).
        """
        # Invalida tokens ativos anteriores
        await self._session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used.is_(False),
            )
            .values(used=True)
        )

        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
        )
        record = PasswordResetToken(
            id=uuid.uuid4(),
            user_id=user_id,
            token=token,
            expires_at=expires_at,
            used=False,
        )
        self._session.add(record)
        await self._session.flush()
        return token

    async def validar_token_reset(self, token: str) -> PasswordResetToken | None:
        """
        Retorna o registro se o token for válido (não usado + não expirado).
        Retorna None se inválido/expirado.
        """
        result = await self._session.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token == token,
                PasswordResetToken.used.is_(False),
                PasswordResetToken.expires_at > datetime.now(timezone.utc),
            )
        )
        return result.scalar_one_or_none()

    async def consumir_token(self, token_record: PasswordResetToken) -> None:
        """Marca o token como usado (idempotente)."""
        token_record.used = True
        self._session.add(token_record)
        await self._session.flush()
