"""loadgen: continuous realistic traffic so metrics are always flowing."""
from __future__ import annotations

import asyncio
import os
import random
import uuid
from contextlib import asynccontextmanager

import httpx

from common.observability import create_app, log

USER_URL = os.getenv("USER_URL", "http://user-service:8000").rstrip("/")
PRODUCT_URL = os.getenv("PRODUCT_URL", "http://product-service:8000").rstrip("/")
CART_URL = os.getenv("CART_URL", "http://cart-service:8000").rstrip("/")
ORDER_URL = os.getenv("ORDER_URL", "http://order-service:8000").rstrip("/")
INTERVAL = float(os.getenv("LOAD_INTERVAL", "0.1"))

running = False
sent = 0
failed = 0


async def traffic_loop() -> None:
    global running, sent, failed
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        username = f"load-{uuid.uuid4().hex[:8]}"
        try:
            await client.post(USER_URL + "/register", json={"username": username, "password": "pw"})
        except Exception:  # noqa: BLE001
            pass
        while running:
            try:
                token = (
                    await client.post(
                        USER_URL + "/login", json={"username": username, "password": "pw"}
                    )
                ).json()["access_token"]
                products = (await client.get(PRODUCT_URL + "/products")).json()["products"]
                product = random.choice(products)
                await client.post(
                    CART_URL + f"/cart/{username}/items",
                    json={"product_id": product["id"], "qty": random.randint(1, 2)},
                )
                await client.post(
                    ORDER_URL + "/orders",
                    json={"user_id": username, "items": [
                        {"product_id": product["id"], "qty": 1}
                    ]},
                    headers={"authorization": f"Bearer {token}"},
                )
                await client.get(
                    PRODUCT_URL + "/products/search", params={"q": product["category"]}
                )
                sent += 4
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.warning("loadgen request failed", extra={"extra_fields": {"error": str(exc)}})
            await asyncio.sleep(INTERVAL)


@asynccontextmanager
async def lifespan(app):
    global running
    running = True
    task = asyncio.create_task(traffic_loop())
    yield
    running = False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = create_app("loadgen", lifespan=lifespan)


@app.get("/stats")
def stats() -> dict:
    return {"sent": sent, "failed": failed, "interval_seconds": INTERVAL}
