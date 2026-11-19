"""Small httpx wrapper that propagates the request id between services."""
from __future__ import annotations

import asyncio
import os

import httpx

from .observability import request_id_var

TIMEOUT = httpx.Timeout(float(os.getenv("HTTP_TIMEOUT", "3.0")))


async def call(
    base_url: str,
    path: str,
    method: str = "GET",
    *,
    json: dict | None = None,
    params: dict | None = None,
    retries: int = 0,
    backoff: float = 0.05,
) -> httpx.Response:
    """Call another service; raise on failure so the caller returns a 5xx.

    `retries` is controlled by ENABLE_RETRY. The Defender AI will later flip
    that flag as a remediation action, so the behaviour is intentionally real.
    """
    url = base_url.rstrip("/") + path
    headers = {"x-request-id": request_id_var.get()}
    attempts = retries + 1
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.request(
                    method, url, json=json, params=params, headers=headers
                )
            response.raise_for_status()
            return response
        except Exception as exc:  # noqa: BLE001 - deliberate: surface as 5xx
            last = exc
            if attempt < attempts - 1:
                await asyncio.sleep(backoff * (2**attempt))
    raise RuntimeError(f"call to {url} failed after {attempts} attempt(s): {last}") from last
