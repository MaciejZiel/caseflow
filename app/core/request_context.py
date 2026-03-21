"""Request-scoped context helpers."""

from __future__ import annotations

from contextvars import ContextVar, Token

from structlog.contextvars import bind_contextvars, clear_contextvars, unbind_contextvars

_REQUEST_ID_KEY = "request_id"
_request_id_var: ContextVar[str | None] = ContextVar(_REQUEST_ID_KEY, default=None)


def set_request_id(request_id: str) -> Token[str | None]:
    token = _request_id_var.set(request_id)
    bind_contextvars(**{_REQUEST_ID_KEY: request_id})
    return token


def clear_request_id(token: Token[str | None] | None = None) -> None:
    if token is not None:
        _request_id_var.reset(token)
    unbind_contextvars(_REQUEST_ID_KEY)
    clear_contextvars()


def get_request_id() -> str | None:
    return _request_id_var.get()
