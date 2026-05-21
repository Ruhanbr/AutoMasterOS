import uuid

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, PlainTextResponse

from app.core.dependencies import DbSession, TenantId
from app.core.exceptions import AutoMasterException, to_http_exception
from app.models.invoice import InvoiceStatus
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.invoice import InvoiceResponse
from app.services.invoice_service import InvoiceService

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("/", response_model=PaginatedResponse)
async def list_invoices(
    tenant_id: TenantId,
    session: DbSession,
    status: InvoiceStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    try:
        result = await InvoiceService(session).list(
            tenant_id, status=status, page=page, page_size=page_size
        )
        return PaginatedResponse(
            items=[InvoiceResponse.model_validate(i) for i in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
            pages=result.pages,
        )
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.get("/service-order/{order_id}", response_model=InvoiceResponse)
async def get_invoice_by_order(
    order_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
):
    try:
        invoice = await InvoiceService(session).get_by_service_order(tenant_id, order_id)
        return InvoiceResponse.model_validate(invoice)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
):
    try:
        invoice = await InvoiceService(session).get(tenant_id, invoice_id)
        return InvoiceResponse.model_validate(invoice)
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.post("/{invoice_id}/retry", response_model=MessageResponse)
async def retry_invoice(
    invoice_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
):
    """Re-processa manualmente uma NF-e em estado ERRO ou REJEITADA."""
    try:
        await InvoiceService(session).retry(tenant_id, invoice_id)
        return MessageResponse(message="NF-e re-encaminhada para processamento")
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.get("/{invoice_id}/xml", response_class=PlainTextResponse)
async def download_xml(
    invoice_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
):
    """Retorna o XML assinado da NF-e autorizada."""
    try:
        xml = await InvoiceService(session).get_xml(tenant_id, invoice_id)
        return PlainTextResponse(content=xml, media_type="application/xml")
    except AutoMasterException as exc:
        raise to_http_exception(exc)


@router.get("/{invoice_id}/danfe")
async def download_danfe(
    invoice_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
):
    """Faz download do DANFE em PDF."""
    try:
        path = await InvoiceService(session).get_danfe_path(tenant_id, invoice_id)
        return FileResponse(
            path=path,
            media_type="application/pdf",
            filename=f"danfe_{invoice_id}.pdf",
        )
    except AutoMasterException as exc:
        raise to_http_exception(exc)
