import io
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.core.dependencies import CurrentUser, DbSession, TenantId
from app.core.exceptions import AutoMasterException, ResourceNotFoundException, to_http_exception
from app.modules.financial.models import EntryType
from app.modules.financial.repository import FinancialEntryRepository
from app.modules.reports.excel_generator import (
    generate_financial_excel,
    generate_stock_excel,
)
from app.modules.reports.os_pdf import generate_os_pdf
from app.modules.reports.whatsapp import build_os_whatsapp_message, build_whatsapp_link
from app.modules.stock.repository import StockItemRepository
from app.repositories.service_order_repository import ServiceOrderRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository

router = APIRouter(tags=["reports"])


@router.get("/service-orders/{order_id}/report/pdf")
async def download_os_pdf(
    order_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
) -> StreamingResponse:
    """Download OS as a professional PDF."""
    try:
        so_repo = ServiceOrderRepository(session)
        order = await so_repo.get_by_id_and_tenant(order_id, tenant_id)
        if order is None:
            raise ResourceNotFoundException("Ordem de Serviço", str(order_id))

        tenant_repo = TenantRepository(session)
        tenant = await tenant_repo.get_by_id(tenant_id)
        tenant_name = tenant.nome_fantasia or tenant.name if tenant else "AutoMaster"

        # Monta endereço formatado da oficina para o cabeçalho do PDF
        def _tenant_address(t) -> str:
            if not t:
                return ""
            parts = []
            if getattr(t, "logradouro", None):
                parts.append(t.logradouro + (f", {t.numero}" if getattr(t, "numero", None) else ""))
            if getattr(t, "bairro", None):
                parts.append(t.bairro)
            city = ""
            if t.municipio:
                city = t.municipio
                if t.uf:
                    city += f"/{t.uf}"
            if city:
                parts.append(city)
            if getattr(t, "cep", None):
                parts.append(f"CEP {t.cep}")
            return " — ".join(parts)

        from decimal import Decimal as _D

        client = order.client
        machine = order.machine

        items_data = [
            {
                "item_type": item.item_type,
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
            }
            for item in (order.items or [])
        ]

        # Busca assinatura do técnico: preferência por technician_user_id (preciso),
        # fallback por nome (OS antigas sem o vínculo direto)
        technician_signature_url: str | None = None
        user_repo = UserRepository(session)
        if order.technician_user_id:
            tecnico = await user_repo.get_by_id(order.technician_user_id)
            if tecnico:
                technician_signature_url = tecnico.assinatura_url
        elif order.technician_name:
            tecnico = await user_repo.get_by_name_and_tenant(
                order.technician_name, tenant_id
            )
            if tecnico:
                technician_signature_url = tecnico.assinatura_url

        # Recomputa totais dos itens para garantir valores corretos no PDF
        def _sum_items(itype: str) -> _D:
            return sum(
                (_D(str(i["total_price"])) for i in items_data if str(i["item_type"]) == itype),
                _D("0.00"),
            )

        pdf_total_services = _sum_items("SERVICO")
        pdf_total_parts = _sum_items("PECA")
        pdf_total_displacement = _sum_items("DESLOCAMENTO")
        pdf_total_discount = _D(str(order.total_discount or "0.00"))
        pdf_total_amount = pdf_total_services + pdf_total_parts + pdf_total_displacement - pdf_total_discount

        # Formata endereço completo do cliente
        def _addr_line(c) -> str | None:
            if not c:
                return None
            parts = []
            if c.logradouro:
                parts.append(c.logradouro + (f", {c.numero}" if c.numero else ""))
            if c.complemento:
                parts.append(c.complemento)
            if c.bairro:
                parts.append(c.bairro)
            city = ""
            if c.municipio:
                city = c.municipio
                if c.uf:
                    city += f"/{c.uf}"
            if city:
                parts.append(city)
            if c.cep:
                parts.append(f"CEP {c.cep}")
            return " — ".join(parts) if parts else None

        order_data = {
            "os_number": order.number,
            "status": order.status,
            "opened_at": order.opened_at,
            "finished_at": order.finished_at,
            "technician_name": order.technician_name,
            "technician_signature_url": technician_signature_url,
            "description": order.description,
            "diagnosis": order.diagnosis,
            "solution": order.solution,
            # Assinatura digital do cliente (aprovação de orçamento)
            "budget_signature": order.budget_signature,
            "budget_signer_name": order.budget_signer_name,
            "budget_signer_document": order.budget_signer_document,
            "budget_approved_at": order.budget_approved_at,
            # Cliente
            "client_name": client.name if client else "—",
            "client_document": client.document if client else "—",
            "client_phone": client.phone if client else "—",
            "client_phone_secondary": client.phone_secondary if client else None,
            "client_fazenda": client.fazenda if client else None,
            "client_address": _addr_line(client),
            "client_inscricao_estadual": client.inscricao_estadual if client else None,
            # Máquina
            "machine_model": machine.model if machine else None,
            "machine_brand": machine.brand if machine else None,
            "machine_serial": machine.serial_number if machine else None,
            "machine_year": machine.year if machine else None,
            "machine_chassis": machine.chassis_number if machine else None,
            "machine_placa": machine.placa if machine else None,
            "machine_proprietario": machine.proprietario if machine else None,
            "machine_horsepower": machine.horsepower if machine else None,
            "machine_engine_number": machine.engine_number if machine else None,
            # Itens e totais
            "items": items_data,
            "total_services": pdf_total_services,
            "total_parts": pdf_total_parts,
            "total_displacement": pdf_total_displacement,
            "total_discount": pdf_total_discount,
            "total_amount": pdf_total_amount,
            "tenant_name": tenant_name,
            "tenant_document": tenant.document if tenant else None,
            "tenant_phone": tenant.phone if tenant else None,
            "tenant_email": tenant.email if tenant else None,
            "tenant_address": _tenant_address(tenant),
            "tenant_logo_url": tenant.logo_url if tenant else None,
            "tenant_city": tenant.municipio if tenant else None,
            "pix_key": tenant.pix_key if tenant else None,
            "pix_key_type": tenant.pix_key_type if tenant else None,
            "generated_at": datetime.now(timezone.utc),
        }

        pdf_bytes = generate_os_pdf(order_data)

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="OS-{order.number}.pdf"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except AutoMasterException as e:
        raise to_http_exception(e)


@router.get("/service-orders/{order_id}/report/whatsapp")
async def get_whatsapp_link(
    order_id: uuid.UUID,
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Returns a WhatsApp wa.me link and pre-filled message for the client."""
    try:
        so_repo = ServiceOrderRepository(session)
        order = await so_repo.get_by_id_and_tenant(order_id, tenant_id)
        if order is None:
            raise ResourceNotFoundException("Ordem de Serviço", str(order_id))

        tenant_repo = TenantRepository(session)
        tenant = await tenant_repo.get_by_id(tenant_id)
        tenant_name = tenant.nome_fantasia or tenant.name if tenant else "AutoMaster"

        client = order.client
        if not client or not client.phone:
            raise AutoMasterException(
                message="Cliente não possui telefone cadastrado",
                code="BUSINESS_RULE_VIOLATION",
            )

        message = build_os_whatsapp_message(
            client_name=client.name,
            os_number=order.number,
            total=f"{order.total_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            workshop_name=tenant_name,
        )
        link = build_whatsapp_link(client.phone, message)

        return {"link": link, "message": message}
    except AutoMasterException as e:
        raise to_http_exception(e)


@router.get("/financial/report/excel")
async def download_financial_excel(
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
    entry_type: Optional[EntryType] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
) -> StreamingResponse:
    """Download financial entries as Excel (.xlsx)."""
    try:
        fin_repo = FinancialEntryRepository(session)
        entries, _ = await fin_repo.list_by_tenant(
            tenant_id,
            entry_type=entry_type,
            date_from=date_from,
            date_to=date_to,
            page=1,
            page_size=10000,  # large page for export
        )
        summary = await fin_repo.get_summary(
            tenant_id, date_from=date_from, date_to=date_to
        )

        entries_data = [
            {
                "id": str(e.id),
                "entry_type": e.entry_type,
                "description": e.description,
                "category": e.category,
                "amount": e.amount,
                "reference_date": e.reference_date,
                "service_order_id": e.service_order_id,
                "notes": e.notes,
                "created_at": e.created_at,
            }
            for e in entries
        ]

        excel_bytes = generate_financial_excel(entries_data, summary)
        filename = f"financeiro_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(excel_bytes)),
            },
        )
    except AutoMasterException as e:
        raise to_http_exception(e)


@router.get("/stock/report/excel")
async def download_stock_excel(
    tenant_id: TenantId,
    session: DbSession,
    current_user: CurrentUser,
) -> StreamingResponse:
    """Download stock items as Excel (.xlsx)."""
    try:
        stock_repo = StockItemRepository(session)
        items, _ = await stock_repo.list_by_tenant(
            tenant_id, page=1, page_size=100000
        )

        items_data = [
            {
                "sku": item.sku,
                "description": item.description,
                "ncm_code": item.ncm_code,
                "unit": item.unit,
                "quantity": item.quantity,
                "min_quantity": item.min_quantity,
                "cost_price": item.cost_price,
                "sale_price": item.sale_price,
                "active": item.active,
                "created_at": item.created_at,
            }
            for item in items
        ]

        excel_bytes = generate_stock_excel(items_data)
        filename = f"estoque_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(excel_bytes)),
            },
        )
    except AutoMasterException as e:
        raise to_http_exception(e)
