"""order-service: orchestrates cart, product and payment, then persists to Postgres."""
from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import HTTPException
from pydantic import BaseModel

from common.db import connect, init_schema
from common.http_client import call
from common.observability import create_app, log

USER_URL = os.getenv("USER_URL", "http://user-service:8000")
PRODUCT_URL = os.getenv("PRODUCT_URL", "http://product-service:8000")
CART_URL = os.getenv("CART_URL", "http://cart-service:8000")
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://payment-service:8000")
RETRIES = 2 if os.getenv("ENABLE_RETRY", "false").lower() == "true" else 0
VERSION = os.getenv("VERSION", "dev")


@asynccontextmanager
async def lifespan(app):
    init_schema()
    log.info("order-service ready", extra={"extra_fields": {"version": VERSION, "retries": RETRIES}})
    yield


app = create_app("order-service", lifespan=lifespan)


class OrderRequest(BaseModel):
    user_id: str
    items: list[dict]


@app.post("/orders")
async def create_order(payload: OrderRequest) -> dict:
    if not payload.user_id or not payload.items:
        raise HTTPException(400, "user_id and items are required")

    enriched: list[dict] = []
    total = 0.0
    for item in payload.items:
        product_id = str(item.get("product_id", ""))
        qty = int(item.get("qty", 1))
        product = (await call(PRODUCT_URL, f"/products/{product_id}", retries=RETRIES)).json()
        enriched.append({"product_id": product_id, "qty": qty, "unit_price": product["price"]})
        total += product["price"] * qty

    cart = (await call(CART_URL, f"/cart/{payload.user_id}", retries=RETRIES)).json()
    payment = (
        await call(
            PAYMENT_URL,
            "/pay",
            "POST",
            json={"user_id": payload.user_id, "amount": round(total, 2)},
            retries=RETRIES,
        )
    ).json()

    order_id = uuid.uuid4().hex[:12]
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO orders (id, user_id, items, total, status, version) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                order_id,
                payload.user_id,
                json.dumps(enriched),
                round(total, 2),
                "paid" if payment.get("ok") else "failed",
                VERSION,
            ),
        )
    return {
        "order_id": order_id,
        "user_id": payload.user_id,
        "items": enriched,
        "cart_snapshot": cart,
        "total": round(total, 2),
        "payment": payment,
        "version": VERSION,
    }


@app.get("/orders/{order_id}")
def get_order(order_id: str) -> dict:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, user_id, items, total, status, version, created_at "
            "FROM orders WHERE id = %s",
            (order_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "order not found")
    return {
        "order_id": row[0],
        "user_id": row[1],
        "items": row[2],
        "total": float(row[3]),
        "status": row[4],
        "version": row[5],
        "created_at": row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
    }
