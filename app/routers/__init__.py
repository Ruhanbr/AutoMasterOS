from app.routers.tenants import router as tenants_router
from app.routers.clients import router as clients_router
from app.routers.machines import router as machines_router
from app.routers.service_orders import router as service_orders_router
from app.routers.invoices import router as invoices_router

__all__ = [
    "tenants_router",
    "clients_router",
    "machines_router",
    "service_orders_router",
    "invoices_router",
]
