from fastapi import HTTPException, status


class AutoMasterException(Exception):
    """Base para todas as exceções de domínio."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class ResourceNotFoundException(AutoMasterException):
    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            message=f"{resource} não encontrado: {identifier}",
            code="NOT_FOUND",
        )
        self.resource = resource
        self.identifier = identifier


class DuplicateResourceException(AutoMasterException):
    def __init__(self, resource: str, field: str, value: str) -> None:
        super().__init__(
            message=f"{resource} já existe com {field}='{value}'",
            code="DUPLICATE_RESOURCE",
        )


class BusinessRuleException(AutoMasterException):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, code="BUSINESS_RULE_VIOLATION")


class InvalidStatusTransitionException(BusinessRuleException):
    def __init__(self, entity: str, current: str, target: str) -> None:
        super().__init__(
            message=f"{entity}: transição de status inválida de '{current}' para '{target}'"
        )
        self.current = current
        self.target = target


class InvoiceAlreadyExistsException(BusinessRuleException):
    def __init__(self, service_order_id: str) -> None:
        super().__init__(
            message=f"NF-e já emitida para a OS {service_order_id}"
        )


class AuthenticationException(AutoMasterException):
    def __init__(self, message: str = "Credenciais inválidas") -> None:
        super().__init__(message=message, code="AUTHENTICATION_ERROR")


class InvoiceProcessingException(AutoMasterException):
    def __init__(self, message: str, sefaz_code: str | None = None) -> None:
        super().__init__(message=message, code="INVOICE_PROCESSING_ERROR")
        self.sefaz_code = sefaz_code


class TenantMismatchException(AutoMasterException):
    def __init__(self) -> None:
        super().__init__(
            message="Acesso negado: recurso pertence a outro tenant",
            code="TENANT_MISMATCH",
        )


class ConcurrencyConflictException(AutoMasterException):
    def __init__(self, resource: str = "recurso") -> None:
        super().__init__(
            message=f"Conflito de concorrência ao atualizar {resource}. Tente novamente.",
            code="CONCURRENCY_CONFLICT",
        )


class ClientOwnershipException(AutoMasterException):
    """Raised when a resource does not belong to the requesting client (403)."""

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            message=f"Acesso negado: {resource} '{identifier}' não pertence ao cliente",
            code="CLIENT_OWNERSHIP_VIOLATION",
        )
        self.resource = resource
        self.identifier = identifier


def to_http_exception(exc: AutoMasterException) -> HTTPException:
    status_map = {
        "NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "DUPLICATE_RESOURCE": status.HTTP_409_CONFLICT,
        "AUTHENTICATION_ERROR": status.HTTP_401_UNAUTHORIZED,
        "BUSINESS_RULE_VIOLATION": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "TENANT_MISMATCH": status.HTTP_403_FORBIDDEN,
        "CLIENT_OWNERSHIP_VIOLATION": status.HTTP_403_FORBIDDEN,
        "INVOICE_PROCESSING_ERROR": status.HTTP_502_BAD_GATEWAY,
        "CONCURRENCY_CONFLICT": status.HTTP_409_CONFLICT,
        "INTERNAL_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    return HTTPException(
        status_code=status_map.get(exc.code, 500),
        detail={"code": exc.code, "message": exc.message},
    )
