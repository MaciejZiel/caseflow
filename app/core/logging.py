"""Structured logging setup."""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.request_context import get_request_id


def configure_logging(debug: bool) -> structlog.stdlib.BoundLogger:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        timestamper,
        _inject_request_id,
    ]

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.DEBUG if debug else logging.INFO,
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger("caseflow")


def _inject_request_id(
    _logger: object, _method_name: str, event_dict: dict[str, object]
) -> dict[str, object]:
    event_dict.setdefault("request_id", get_request_id())
    return event_dict
