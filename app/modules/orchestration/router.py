import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DbSession, TenantId
from app.core.exceptions import AutoMasterException, to_http_exception
from app.modules.orchestration.finalize_complete import FinalizeCompleteUseCase
from app.schemas.service_order import ServiceOrderResponse

router = APIRouter(tags=["orchestration"])


@router.post(
    "/service-orders/{order_id}/finalize-complete",
    response_model=ServiceOrderResponse,
)
async def finalize_complete(
    order_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    notes: Optional[str] = Query(None),
    reduce_stock: bool = Query(True),
) -> ServiceOrderResponse:
    """
    Finalize an OS atomically with stock reduction and financial entry.

    Wraps all operations in a single transaction:
    - OS status → FINALIZADA
    - Stock reduced for each PECA item (if reduce_stock=True)
    - Financial RECEITA entry created (idempotent)
    - Invoice created (PENDENTE)

    After commit, dispatches Celery task for NF-e emission.
    """
    try:
        use_case = FinalizeCompleteUseCase(session)
        order = await use_case.finalize_with_stock_and_financial(
            tenant_id=tenant_id,
            order_id=order_id,
            notes=notes,
            reduce_stock=reduce_stock,
        )
    except AutoMasterException as e:
        raise to_http_exception(e)

    # Dispatch Celery task AFTER the use case (outside transaction, after flush)
    # The session commits when this request handler returns
    try:
        from app.repositories.invoice_repository import InvoiceRepository
        invoice_repo = InvoiceRepository(session)
        invoice = await invoice_repo.get_by_service_order_id(order_id)

        if invoice is not None:
            import hashlib
            idempotency_key = hashlib.sha256(f"nfe:{order_id}".encode()).hexdigest()
            from app.workers.tasks import process_invoice_task

            process_invoice_task.apply_async(
                kwargs={
                    "invoice_id": str(invoice.id),
                    "idempotency_key": idempotency_key,
                },
                queue="nfe",
                countdown=2,
            )
    except Exception as celery_exc:
        # Celery dispatch failure must NOT roll back the DB transaction
        import logging
        logging.getLogger(__name__).warning(
            "celery_dispatch_failed_after_finalize",
            extra={"order_id": str(order_id), "error": str(celery_exc)},
        )

    return ServiceOrderResponse.model_validate(order)
