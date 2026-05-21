from functools import lru_cache
from typing import Literal
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "AutoMaster"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_DEBUG: bool = False
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    API_V1_PREFIX: str = "/api/v1"

    # ─── JWT ──────────────────────────────────────────────────────────────────
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ─── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://automaster:automaster@localhost:5432/automaster"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://automaster:automaster@localhost:5432/automaster"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # ─── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ─── Celery ───────────────────────────────────────────────────────────────
    CELERY_TASK_MAX_RETRIES: int = 5
    CELERY_TASK_RETRY_BACKOFF: int = 60
    CELERY_TASK_RETRY_BACKOFF_MAX: int = 3600
    CELERY_TASK_SOFT_TIME_LIMIT: int = 300
    CELERY_TASK_TIME_LIMIT: int = 600

    # ─── SEFAZ ────────────────────────────────────────────────────────────────
    SEFAZ_AMBIENTE: int = 2
    SEFAZ_UF: str = "SP"
    SEFAZ_TIMEOUT: int = 30
    SEFAZ_MOCK_ENABLED: bool = True
    SEFAZ_WEBSERVICE_URL: str = "https://homologacao.nfe.fazenda.sp.gov.br/ws"

    # ─── Certificado Digital ──────────────────────────────────────────────────
    CERT_PATH: str = "/certs/certificado.pfx"
    CERT_PASSWORD: str = ""

    # ─── Fiscal ───────────────────────────────────────────────────────────────
    REGIME_TRIBUTARIO: int = 1
    CNPJ_EMITENTE: str = "00000000000000"
    RAZAO_SOCIAL_EMITENTE: str = "OFICINA AGRICOLA LTDA"
    NOME_FANTASIA_EMITENTE: str = "AutoMaster"
    IE_EMITENTE: str = "000000000000"
    CRT: str = "1"

    # ─── Storage ──────────────────────────────────────────────────────────────
    STORAGE_PATH: str = "/storage"
    XML_OUTPUT_PATH: str = "/storage/xml"
    DANFE_OUTPUT_PATH: str = "/storage/danfe"

    # ─── Logging ──────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True

    # ─── Email ────────────────────────────────────────────────────────────────
    EMAIL_HOST: str = "smtp.gmail.com"
    EMAIL_PORT: int = 587
    EMAIL_USER: str = ""
    EMAIL_PASS: str = ""
    EMAIL_FROM: str = "noreply@automaster.com"
    EMAIL_FROM_NAME: str = "AutoMaster"
    EMAIL_ENABLED: bool = False  # False em dev → só loga o conteúdo
    # URL base do frontend (usada nos links de email)
    APP_URL: str = "http://localhost:3000"
    # Expiração do token de reset (minutos)
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 60

    @field_validator("CNPJ_EMITENTE")
    @classmethod
    def validate_cnpj(cls, v: str) -> str:
        digits = "".join(filter(str.isdigit, v))
        if len(digits) != 14:
            raise ValueError("CNPJ_EMITENTE deve ter 14 dígitos")
        return digits

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
