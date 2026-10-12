"""Domain exceptions that map cleanly to HTTP responses.

Raise these from services and routers — the FastAPI exception handlers in main.py
turn them into RFC 7807 problem+json responses.
"""


class DomainError(Exception):
    """Base. Carries an HTTP status and machine-readable code."""

    status_code: int = 400
    code: str = "domain_error"

    def __init__(self, message: str, *, detail: dict | None = None):
        super().__init__(message)
        self.detail = detail or {}


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class Forbidden(DomainError):
    status_code = 403
    code = "forbidden"


class Unauthorized(DomainError):
    status_code = 401
    code = "unauthorized"


class Conflict(DomainError):
    status_code = 409
    code = "conflict"


class ValidationFailed(DomainError):
    status_code = 422
    code = "validation_failed"


class ApprovalChainError(DomainError):
    """Raised by the approval engine for lifecycle/state violations."""

    status_code = 409
    code = "approval_chain_error"
