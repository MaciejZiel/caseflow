"""Application-level exceptions."""

from __future__ import annotations


class CaseFlowError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(CaseFlowError):
    def __init__(self, entity_name: str, message: str | None = None) -> None:
        super().__init__(
            code=f"{entity_name}_not_found",
            message=message or f"{entity_name.replace('_', ' ').title()} does not exist.",
            status_code=404,
        )


class PermissionDeniedError(CaseFlowError):
    def __init__(self, message: str = "You do not have permission to perform this action.") -> None:
        super().__init__(code="permission_denied", message=message, status_code=403)


class ConflictError(CaseFlowError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=409)


class AuthenticationError(CaseFlowError):
    def __init__(self, message: str = "Authentication failed.") -> None:
        super().__init__(code="authentication_failed", message=message, status_code=401)


class DomainValidationError(CaseFlowError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=400)
