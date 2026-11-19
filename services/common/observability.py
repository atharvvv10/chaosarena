"""Shared observability helpers for all ShopApp services.

Gives every service:
  * structured JSON logs with a propagated request id
  * Prometheus counters/histograms
  * /health, /ready and /metrics endpoints
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
SERVICE_NAME = os.getenv("SERVICE_NAME", "unknown")
VERSION = os.getenv("VERSION", "dev")

REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "method", "path", "status"],
)
ERRORS = Counter(
    "http_errors_total",
    "Total HTTP 5xx responses",
    ["service", "method", "path", "status"],
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["service", "method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

log = logging.getLogger("shopapp")


class JsonFormatter(logging.Formatter):
    """One JSON object per log line, including the current request id."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": SERVICE_NAME,
            "version": VERSION,
            "request_id": request_id_var.get(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = value
        return json.dumps(payload)


def setup_logging() -> None:
    """Configure the root shopapp logger exactly once."""
    if getattr(log, "_chaosarena_configured", False):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    log.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    log.handlers = [handler]
    log.propagate = False
    setattr(log, "_chaosarena_configured", True)


def create_app(service_name: str, lifespan: Callable | None = None) -> FastAPI:
    """Build a FastAPI app with the standard ops endpoints and middleware."""
    global SERVICE_NAME
    SERVICE_NAME = service_name
    os.environ["SERVICE_NAME"] = service_name
    setup_logging()

    app = FastAPI(title=service_name, version=VERSION, lifespan=lifespan)

    def _record(method: str, path: str, status: int, started: float) -> None:
        duration = time.perf_counter() - started
        REQUESTS.labels(service_name, method, path, str(status)).inc()
        LATENCY.labels(service_name, method, path).observe(duration)
        if status >= 500:
            ERRORS.labels(service_name, method, path, str(status)).inc()
        log.info(
            "http_request",
            extra={"extra_fields": {
                "method": method,
                "path": path,
                "status": status,
                "duration_ms": round(duration * 1000, 2),
            }},
        )

    @app.middleware("http")
    async def observability(request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        token = request_id_var.set(rid)
        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
            response.headers["x-request-id"] = rid
        except Exception:
            _record(request.method, request.url.path, 500, started)
            request_id_var.reset(token)
            raise
        _record(request.method, request.url.path, response.status_code, started)
        request_id_var.reset(token)
        return response

    @app.get("/health", tags=["ops"])
    def health() -> dict:
        return {"status": "up", "service": service_name, "version": VERSION}

    @app.get("/ready", tags=["ops"])
    def ready() -> dict:
        return {"status": "ready", "service": service_name, "version": VERSION}

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
