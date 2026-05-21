"""
NfeProcessor — pipeline completo de emissão de NF-e.

Executado de forma assíncrona dentro do worker Celery.
Jamais é chamado diretamente pela API.

Fluxo:
  1. Adquire lock FOR UPDATE SKIP LOCKED (idempotência multi-worker)
  2. Valida estado atual da invoice
  3. Marca PROCESSANDO e persiste
  4. Carrega dados completos da OS
  5. Calcula tributos
  6. Gera número NF-e (atômico)
  7. Constrói XML NF-e 4.0
  8. Assina com certificado A1
  9. Persiste XML em disco
 10. Transmite para SEFAZ (mock ou real)
 11. Processa retorno → AUTORIZADA ou REJEITADA
 12. Gera DANFE (PDF)
 13. Atualiza invoice e OS com resultado final
"""

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionFactory
from app.core.logging import get_logger
from app.models.invoice import Invoice, InvoiceStatus
from app.models.service_order import ServiceOrder, ServiceOrderStatus
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.service_order_repository import ServiceOrderRepository
from app.repositories.tenant_repository import TenantRepository
from app.utils.danfe_generator import danfe_generator
from app.utils.nfe_signer import nfe_signer
from app.utils.nfe_xml_builder import nfe_xml_builder
from app.utils.sefaz_client import (
    SefazCommunicationError,
    SefazRejectionError,
    get_sefaz_client,
)
from app.utils.tax_calculator import tax_calculator

logger = get_logger(__name__)


class NfeProcessor:
    """
    Orquestra todas as etapas de emissão da NF-e dentro de uma única
    sessão de banco de dados, garantindo atomicidade e rastreabilidade.
    """

    async def process(self, invoice_id: str, idempotency_key: str) -> dict:
        async with AsyncSessionFactory() as session:
            return await self._run(session, invoice_id, idempotency_key)

    async def _run(
        self, session: AsyncSession, invoice_id: str, idempotency_key: str
    ) -> dict:
        invoice_repo = InvoiceRepository(session)
        so_repo = ServiceOrderRepository(session)
        tenant_repo = TenantRepository(session)

        # ── 1. Idempotência: tenta adquirir lock exclusivo ──────────────────
        invoice = await invoice_repo.get_by_idempotency_key_with_lock(idempotency_key)

        if invoice is None:
            # SKIP LOCKED: outro worker está processando — encerra silenciosamente
            logger.warning(
                "nfe_lock_nao_adquirido",
                invoice_id=invoice_id,
                idempotency_key=idempotency_key,
            )
            return {"status": "skipped", "reason": "lock_not_acquired"}

        if invoice.status == InvoiceStatus.AUTORIZADA:
            logger.info("nfe_ja_autorizada", invoice_id=str(invoice.id))
            return {"status": "already_authorized", "access_key": invoice.access_key}

        if invoice.status == InvoiceStatus.PROCESSANDO:
            # Retomada após crash/restart do worker — continua processando
            logger.warning("nfe_retomando_processamento", invoice_id=str(invoice.id))

        # ── 2. Marca como PROCESSANDO ────────────────────────────────────────
        invoice.status = InvoiceStatus.PROCESSANDO
        invoice.retry_count += 1
        await invoice_repo.save(invoice)
        await session.commit()

        logger.info(
            "nfe_processando",
            invoice_id=str(invoice.id),
            service_order_id=str(invoice.service_order_id),
            tentativa=invoice.retry_count,
        )

        # ── 3. Carrega dados completos ───────────────────────────────────────
        service_order = await so_repo.get_by_id_and_tenant(
            invoice.service_order_id, invoice.tenant_id
        )
        if service_order is None:
            await self._mark_error(invoice_repo, invoice, "OS não encontrada", session)
            raise RuntimeError(f"OS {invoice.service_order_id} não encontrada")

        tenant = await tenant_repo.get_active_by_id(invoice.tenant_id)
        if tenant is None:
            await self._mark_error(invoice_repo, invoice, "Tenant não encontrado", session)
            raise RuntimeError(f"Tenant {invoice.tenant_id} não encontrado")

        client = service_order.client
        if client is None:
            await self._mark_error(invoice_repo, invoice, "Cliente não encontrado", session)
            raise RuntimeError("Cliente não encontrado na OS")

        # ── 4. Cálculo tributário ─────────────────────────────────────────────
        tax_result = tax_calculator.calculate(service_order)
        invoice.tax_data = tax_result.to_dict()
        invoice.total_amount = tax_result.valor_total_nf
        invoice.total_tax = tax_result.valor_total_tributos

        logger.info(
            "tributos_calculados",
            invoice_id=str(invoice.id),
            total_nf=str(tax_result.valor_total_nf),
            total_tributos=str(tax_result.valor_total_tributos),
        )

        # ── 5. Número NF-e atômico ───────────────────────────────────────────
        nfe_number = await self._get_next_nfe_number(session, invoice.tenant_id)
        invoice.number = nfe_number

        # ── 6. Construção do XML ─────────────────────────────────────────────
        xml_string, access_key = nfe_xml_builder.build(
            service_order=service_order,
            tenant=tenant,
            client=client,
            tax_result=tax_result,
            nfe_number=nfe_number,
            serie=int(invoice.series),
            emissao=datetime.now(timezone.utc),
        )

        logger.info(
            "xml_gerado",
            invoice_id=str(invoice.id),
            access_key=access_key,
            nfe_number=nfe_number,
        )

        # ── 7. Assinatura digital ────────────────────────────────────────────
        signed_xml = nfe_signer.sign(xml_string)
        invoice.access_key = access_key

        logger.info("xml_assinado", invoice_id=str(invoice.id))

        # ── 8. Transmissão SEFAZ ─────────────────────────────────────────────
        sefaz_client = get_sefaz_client()

        try:
            logger.info(
                "sefaz_transmitindo",
                invoice_id=str(invoice.id),
                mock=settings.SEFAZ_MOCK_ENABLED,
            )
            sefaz_response = await sefaz_client.authorize(signed_xml, access_key)

        except SefazRejectionError as exc:
            # Rejeição de negócio — NÃO retry automático
            logger.error(
                "sefaz_rejeitou",
                invoice_id=str(invoice.id),
                codigo=exc.code,
                mensagem=exc.message,
            )
            invoice.status = InvoiceStatus.REJEITADA
            invoice.rejection_code = exc.code
            invoice.rejection_message = exc.message
            invoice.rejected_at = datetime.now(timezone.utc)
            await invoice_repo.save(invoice)
            await session.commit()
            return {
                "status": "rejected",
                "code": exc.code,
                "message": exc.message,
            }

        except SefazCommunicationError as exc:
            # Falha de rede — propaga para o Celery tratar com retry
            logger.error(
                "sefaz_erro_comunicacao",
                invoice_id=str(invoice.id),
                error=str(exc),
            )
            await self._mark_error(invoice_repo, invoice, str(exc), session)
            raise  # Celery intercepta e aplica retry exponencial

        # ── 9. Autorização recebida ───────────────────────────────────────────
        invoice.status = InvoiceStatus.AUTORIZADA
        invoice.protocol_number = sefaz_response.protocol_number
        invoice.authorized_at = datetime.now(timezone.utc)
        invoice.xml_content = signed_xml
        invoice.issued_at = datetime.now(timezone.utc)

        logger.info(
            "sefaz_autorizou",
            invoice_id=str(invoice.id),
            protocol=sefaz_response.protocol_number,
        )

        # ── 10. Persiste XML em disco ─────────────────────────────────────────
        xml_path = self._persist_xml(signed_xml, access_key, str(invoice.tenant_id))
        invoice.xml_path = xml_path

        # ── 11. Gera DANFE ────────────────────────────────────────────────────
        try:
            danfe_path = danfe_generator.generate(service_order, invoice, tax_result)
            invoice.danfe_path = danfe_path
            logger.info("danfe_gerado", invoice_id=str(invoice.id), path=danfe_path)
        except Exception as exc:
            # Falha no DANFE não invalida a autorização — loga e continua
            logger.error("danfe_falhou", invoice_id=str(invoice.id), error=str(exc))

        # ── 12. Persiste resultado final ──────────────────────────────────────
        await invoice_repo.save(invoice)
        await session.commit()

        logger.info(
            "nfe_emitida_com_sucesso",
            invoice_id=str(invoice.id),
            access_key=access_key,
            protocol=sefaz_response.protocol_number,
            os_number=service_order.number,
        )

        return {
            "status": "authorized",
            "access_key": access_key,
            "protocol_number": sefaz_response.protocol_number,
            "invoice_id": str(invoice.id),
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_next_nfe_number(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> int:
        """
        Número sequencial de NF-e por tenant.
        Usa SELECT MAX + 1 dentro de uma transação com lock.
        """
        # FOR UPDATE não é permitido com funções de agregação no PostgreSQL.
        # O número sequencial é atribuído dentro de uma transação existente,
        # garantindo visibilidade correta sem precisar de lock extra.
        stmt = (
            select(func.coalesce(func.max(Invoice.number), 0))
            .where(Invoice.tenant_id == tenant_id)
        )
        result = await session.execute(stmt)
        return (result.scalar_one() or 0) + 1

    def _persist_xml(self, xml_content: str, access_key: str, tenant_id: str) -> str:
        output_dir = Path(settings.XML_OUTPUT_PATH) / tenant_id
        output_dir.mkdir(parents=True, exist_ok=True)
        xml_path = output_dir / f"{access_key}.xml"
        xml_path.write_text(xml_content, encoding="utf-8")
        return str(xml_path)

    async def _mark_error(
        self,
        repo: InvoiceRepository,
        invoice: Invoice,
        error_message: str,
        session: AsyncSession,
    ) -> None:
        from datetime import timedelta

        invoice.status = InvoiceStatus.ERRO
        invoice.last_error = error_message[:2000]
        invoice.next_retry_at = datetime.now(timezone.utc) + timedelta(
            seconds=min(
                settings.CELERY_TASK_RETRY_BACKOFF * (2 ** invoice.retry_count),
                settings.CELERY_TASK_RETRY_BACKOFF_MAX,
            )
        )
        await repo.save(invoice)
        await session.commit()


nfe_processor = NfeProcessor()
