"""
Configuração do Celery para o AutoMaster.

Filas:
  nfe     — processamento de NF-e (alta prioridade, workers dedicados)
  default — tarefas gerais

Garantias:
  - acks_late=True        → task só confirmada após execução
  - reject_on_worker_lost → recoloca na fila se o worker cair abruptamente
  - prefetch_multiplier=1 → cada worker pega 1 task por vez (evita acúmulo)
"""

from celery import Celery
from celery.utils.log import get_task_logger
from kombu import Exchange, Queue

from app.core.config import settings

logger = get_task_logger(__name__)

celery_app = Celery(
    "automaster",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

_nfe_exchange = Exchange("nfe", type="direct", durable=True)
_default_exchange = Exchange("default", type="direct", durable=True)

celery_app.conf.update(
    # ── Serialização ──────────────────────────────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # ── Timezone ──────────────────────────────────────────────────────────────
    timezone="America/Sao_Paulo",
    enable_utc=True,
    # ── Confiabilidade ────────────────────────────────────────────────────────
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    # ── Timeouts ──────────────────────────────────────────────────────────────
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    # ── Filas ─────────────────────────────────────────────────────────────────
    task_queues=(
        Queue(
            "nfe",
            exchange=_nfe_exchange,
            routing_key="nfe",
            queue_arguments={"x-max-priority": 10},
        ),
        Queue("default", exchange=_default_exchange, routing_key="default"),
    ),
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
    task_routes={
        "workers.process_invoice": {"queue": "nfe", "routing_key": "nfe"},
        "workers.retry_failed_invoices": {"queue": "nfe", "routing_key": "nfe"},
    },
    # ── Beat Schedule (tarefas periódicas) ───────────────────────────────────
    beat_schedule={
        "retry-failed-invoices-every-5min": {
            "task": "workers.retry_failed_invoices",
            "schedule": 300.0,  # a cada 5 minutos
            "options": {"queue": "nfe"},
        },
        "deere-poll-alerts-every-30min": {
            "task": "workers.poll_deere_alerts",
            "schedule": 1800.0,  # a cada 30 minutos
            "options": {"queue": "default"},
        },
    },
    # ── Resultados ────────────────────────────────────────────────────────────
    result_expires=86400,   # resultados expiram em 24h
    result_persistent=True,
    # ── Retry padrão ─────────────────────────────────────────────────────────
    task_max_retries=settings.CELERY_TASK_MAX_RETRIES,
)
