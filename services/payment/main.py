"""payment-service: simulated payments with configurable latency and failure rate."""
from __future__ import annotations

import asyncio
import os
import random
import uuid

from fastapi import HTTPException
from pydantic import BaseModel

from common.observability import create_app

app = create_app("payment-service")
FAILURE_RATE = float(os.getenv("PAYMENT_FAILURE_RATE", "0.01"))
LATENCY_MIN = float(os.getenv("PAYMENT_LATENCY_MIN", "0.01"))
LATENCY_MAX = float(os.getenv("PAYMENT_LATENCY_MAX", "0.12"))


class PaymentRequest(BaseModel):
    user_id: str
    amount: float


@app.post("/pay")
async def pay(payload: PaymentRequest) -> dict:
    latency = random.uniform(LATENCY_MIN, LATENCY_MAX)
    await asyncio.sleep(latency)
    if random.random() < FAILURE_RATE:
        raise HTTPException(503, "payment gateway temporarily unavailable")
    return {
        "ok": True,
        "transaction_id": uuid.uuid4().hex[:12],
        "user_id": payload.user_id,
        "amount": round(payload.amount, 2),
        "gateway_latency_ms": round(latency * 1000, 1),
    }
