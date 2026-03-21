"""Prometheus metrics for HTTP traffic and background jobs."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

HTTP_REQUESTS_TOTAL = Counter(
    "caseflow_http_requests_total",
    "Total number of HTTP requests handled by the API.",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "caseflow_http_request_duration_seconds",
    "Latency of HTTP requests handled by the API.",
    ["method", "path"],
)

HTTP_ERRORS_TOTAL = Counter(
    "caseflow_http_errors_total",
    "Total number of HTTP responses with server error status.",
    ["method", "path", "status_code"],
)


def record_http_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    labels = {"method": method, "path": path, "status_code": str(status_code)}
    HTTP_REQUESTS_TOTAL.labels(**labels).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration_seconds)


def record_http_error(method: str, path: str, status_code: int) -> None:
    HTTP_ERRORS_TOTAL.labels(
        method=method,
        path=path,
        status_code=str(status_code),
    ).inc()
