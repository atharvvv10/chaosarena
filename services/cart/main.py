"""cart-service: Redis-backed shopping cart."""
from __future__ import annotations

import os

import redis
from fastapi import HTTPException
from pydantic import BaseModel

from common.observability import create_app

app = create_app("cart-service")
client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    db=0,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)


class ItemRequest(BaseModel):
    product_id: str
    qty: int = 1


def _key(user_id: str) -> str:
    return f"cart:{user_id}"


def _read(user_id: str) -> dict:
    raw = client.hgetall(_key(user_id))
    return {
        "user_id": user_id,
        "items": [{"product_id": k, "qty": int(v)} for k, v in sorted(raw.items())],
    }


@app.post("/cart/{user_id}/items")
def add_item(user_id: str, payload: ItemRequest) -> dict:
    if payload.qty < 1:
        raise HTTPException(400, "qty must be >= 1")
    client.hincrby(_key(user_id), payload.product_id, payload.qty)
    return _read(user_id)


@app.get("/cart/{user_id}")
def get_cart(user_id: str) -> dict:
    return _read(user_id)


@app.delete("/cart/{user_id}/items/{product_id}")
def remove_item(user_id: str, product_id: str) -> dict:
    client.hdel(_key(user_id), product_id)
    return _read(user_id)


@app.post("/cart/{user_id}/clear")
def clear_cart(user_id: str) -> dict:
    client.delete(_key(user_id))
    return _read(user_id)
