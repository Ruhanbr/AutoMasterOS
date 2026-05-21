"""
Tasks Celery do AutoMaster.

process_invoice_task — task principal de emissão de NF-e
retry_failed_invoices — beat periódico que re-despacha NFs com falha
"""

import asyncio
from datetime import datetime, timezone

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger

from app.core.config import settings
from app.utils.sefaz_client import SefazCommunicationError
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


# ─── Task Principal ───────────────────────────────────────────────────────────

@celery_app.task(
    name="workers.process_invoice",
    bind=True,
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
    soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    time_limit=settings.CELERY_TASK_TIME_LIMIT,
    acks_late=True,
    reject_on_worker_lost=True,
    default_retry_delay=settings.CELERY_TASK_RETRY_BACKOFF,
)
def process_invoice_task(self: Task, invoice_id: str, idempotency_key: str) -> dict:
    """
    Processa a emissão da NF-e de forma resiliente com retry exponencial.

    Regras de retry:
      - SefazCommunicationError → retry exponencial (rede/timeout)
      - SoftTimeLimitExceeded   → retry (worker excedeu tempo)
      - Qualquer Exception      → marca ERRO, retry exponencial
      - SefazRejectionError     → NÃO retry (rejeição de negócio)
    """
    from app.workers.nfe_processor import nfe_processor

    logger.info(
        "task_iniciada",
        invoice_id=invoice_id,
        idempotency_key=idempotency_key,
        tentativa=self.request.retries + 1,
        max_tentativas=self.max_retries + 1,
    )

    try:
        result = asyncio.run(
            nfe_processor.process(invoice_id, idempotency_key)
        )
        logger.info(
            "task_concluida",
            invoice_id=invoice_id,
            result_status=result.get("status"),
        )
        return result

    except SefazCommunicationError as exc:
        retry_in = _exponential_backoff(self.request.retries)
        logger.warning(
            "task_retry_sefaz",
            invoice_id=invoice_id,
            tentativa=self.request.retries + 1,
            proximo_retry_em=retry_in,
            error=str(exc),
        )
        raise self.retry(exc=exc, countdown=retry_in)

    except SoftTimeLimitExceeded:
        retry_in = _exponential_backoff(self.request.retries)
        logger.error(
            "task_soft_timeout",
            invoice_id=invoice_id,
            retry_em=retry_in,
        )
        raise self.retry(
            exc=SoftTimeLimitExceeded("Soft time limit excedido"),
            countdown=retry_in,
        )

    except Exception as exc:
        retry_in = _exponential_backoff(self.request.retries)
        logger.error(
            "task_erro_inesperado",
            invoice_id=invoice_id,
            tentativa=self.request.retries + 1,
            error=str(exc),
            exc_type=type(exc).__name__,
            retry_em=retry_in,
        )
        if self.request.retries >= self.max_retries:
            logger.error(
                "task_esgotou_tentativas",
                invoice_id=invoice_id,
                max_retries=self.max_retries,
            )
            return {"status": "failed", "error": str(exc)}

        raise self.retry(exc=exc, countdown=retry_in)


# ─── Beat: reprocessamento periódico ─────────────────────────────────────────

@celery_app.task(name="workers.retry_failed_invoices")
def retry_failed_invoices() -> dict:
    """
    Executada pelo Celery Beat a cada 5 minutos.
    Busca NFs em ERRO elegíveis para retry e re-despacha a task.

    Garante que NFs não fiquem presas em caso de falha não tratada.
    """
    from app.core.database import AsyncSessionFactory
    from app.repositories.invoice_repository import InvoiceRepository

    async def _find_and_dispatch() -> int:
        dispatched = 0
        async with AsyncSessionFactory() as session:
            repo = InvoiceRepository(session)
            invoices = await repo.list_retriable(
                max_retries=settings.CELERY_TASK_MAX_RETRIES
            )
            for invoice in invoices:
                process_invoice_task.apply_async(
                    kwargs={
                        "invoice_id": str(invoice.id),
                        "idempotency_key": invoice.idempotency_key,
                    },
                    queue="nfe",
                )
                dispatched += 1
                logger.info(
                    "beat_retry_despachado",
                    invoice_id=str(invoice.id),
                    retry_count=invoice.retry_count,
                )
        return dispatched

    count = asyncio.run(_find_and_dispatch())
    logger.info("beat_retry_concluido", total_despachados=count)
    return {"dispatched": count, "at": datetime.now(timezone.utc).isoformat()}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _exponential_backoff(retry_number: int) -> int:
    """
    Calcula o intervalo de retry com backoff exponencial.
    Fórmula: min(base * 2^n, max_backoff)
    """
    base = settings.CELERY_TASK_RETRY_BACKOFF
    max_backoff = settings.CELERY_TASK_RETRY_BACKOFF_MAX
    delay = base * (2 ** retry_number)
    return min(delay, max_backoff)
