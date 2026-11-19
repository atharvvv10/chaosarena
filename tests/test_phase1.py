"""Phase 1 acceptance tests: every service behaves correctly in isolation."""
from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
# Shared ops endpoints / observability
# --------------------------------------------------------------------------- #
def test_product_ops_endpoints():
    from product.main import app

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["service"] == "product-service"

        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["version"]

        client.get("/products")
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "http_requests_total" in metrics.text
        assert "http_request_duration_seconds_bucket" in metrics.text


def test_request_id_is_propagated():
    from product.main import app

    with TestClient(app) as client:
        response = client.get("/products", headers={"x-request-id": "demo-123"})
        assert response.headers["x-request-id"] == "demo-123"


# --------------------------------------------------------------------------- #
# user-service
# --------------------------------------------------------------------------- #
def test_user_register_login_jwt():
    from user.main import SECRET, app

    with TestClient(app) as client:
        created = client.post("/register", json={"username": "alice", "password": "pw"})
        assert created.status_code == 200
        user_id = created.json()["user_id"]
        assert user_id

        duplicate = client.post("/register", json={"username": "alice", "password": "pw"})
        assert duplicate.status_code == 409

        bad = client.post("/login", json={"username": "alice", "password": "wrong"})
        assert bad.status_code == 401

        logged = client.post("/login", json={"username": "alice", "password": "pw"})
        assert logged.status_code == 200
        token = logged.json()["access_token"]
        assert jwt.decode(token, SECRET, algorithms=["HS256"])["sub"] == "alice"

        fetched = client.get(f"/users/{user_id}")
        assert fetched.json()["username"] == "alice"


# --------------------------------------------------------------------------- #
# product-service
# --------------------------------------------------------------------------- #
def test_product_list_search_and_404():
    from product.main import app

    with TestClient(app) as client:
        listing = client.get("/products").json()
        assert listing["count"] == 12
        assert len(listing["products"]) == 12

        filtered = client.get("/products", params={"category": "books"}).json()
        assert filtered["count"] == 3
        assert all(p["category"] == "books" for p in filtered["products"])

        search = client.get("/products/search", params={"q": "Product 1"}).json()
        assert search["count"] >= 1

        assert client.get("/products/does-not-exist").status_code == 404


# --------------------------------------------------------------------------- #
# payment-service
# --------------------------------------------------------------------------- #
def test_payment_success(monkeypatch):
    from payment import main as payment

    monkeypatch.setattr(payment.random, "uniform", lambda a, b: 0.0)
    monkeypatch.setattr(payment.random, "random", lambda: 0.99)

    with TestClient(payment.app) as client:
        result = client.post("/pay", json={"user_id": "u1", "amount": 12.5})
        assert result.status_code == 200
        body = result.json()
        assert body["ok"] is True
        assert body["amount"] == 12.5
        assert len(body["transaction_id"]) == 12


def test_payment_failure_counts_as_error(monkeypatch):
    from payment import main as payment

    monkeypatch.setattr(payment.random, "uniform", lambda a, b: 0.0)
    monkeypatch.setattr(payment.random, "random", lambda: 0.0)

    with TestClient(payment.app) as client:
        assert client.post("/pay", json={"user_id": "u1", "amount": 5}).status_code == 503
        metrics = client.get("/metrics").text
        error_lines = [
            line for line in metrics.splitlines()
            if line.startswith("http_errors_total{") and "payment-service" in line
        ]
        assert error_lines, "payment 5xx responses must increment http_errors_total"
        assert any(float(line.rsplit(" ", 1)[-1]) >= 1 for line in error_lines)


# --------------------------------------------------------------------------- #
# cart-service (uses fakeredis so it runs without a Redis server)
# --------------------------------------------------------------------------- #
def test_cart_lifecycle(monkeypatch):
    import fakeredis
    from cart import main as cart

    monkeypatch.setattr(cart, "client", fakeredis.FakeRedis(decode_responses=True))

    with TestClient(cart.app) as client:
        added = client.post(
            "/cart/alice/items", json={"product_id": "p1", "qty": 2}
        ).json()
        assert added["items"] == [{"product_id": "p1", "qty": 2}]

        added_again = client.post(
            "/cart/alice/items", json={"product_id": "p1", "qty": 3}
        ).json()
        assert added_again["items"][0]["qty"] == 5

        assert client.get("/cart/alice").json()["items"][0]["qty"] == 5

        removed = client.delete("/cart/alice/items/p1").json()
        assert removed["items"] == []

        client.post("/cart/alice/items", json={"product_id": "p2", "qty": 1})
        assert client.post("/cart/alice/clear").json()["items"] == []


# --------------------------------------------------------------------------- #
# order-service (dependencies mocked; verifies orchestration + SQL insert)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def order_client(monkeypatch):
    from order import main as order

    executed: list[tuple[str, tuple | None]] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            executed.append((sql, params))

        def fetchone(self):
            return None

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return FakeCursor()

    class FakeResponse:
        def __init__(self, data: dict):
            self._data = data

        def json(self) -> dict:
            return self._data

        def raise_for_status(self) -> None:
            return None

    async def fake_call(base_url, path, method="GET", **kwargs):
        if "/products/" in path:
            return FakeResponse({"price": 10.0})
        if "/cart/" in path:
            return FakeResponse({"items": []})
        if "/pay" in path:
            return FakeResponse({"ok": True, "transaction_id": "txn123"})
        return FakeResponse({})

    monkeypatch.setattr(order, "init_schema", lambda: None)
    monkeypatch.setattr(order, "connect", lambda: FakeConn())
    monkeypatch.setattr(order, "call", fake_call)

    with TestClient(order.app) as client:
        yield client, executed


def test_order_orchestration(order_client):
    client, executed = order_client
    response = client.post(
        "/orders",
        json={"user_id": "alice", "items": [{"product_id": "p1", "qty": 2}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 20.0
    assert body["items"][0]["unit_price"] == 10.0
    assert body["payment"]["transaction_id"] == "txn123"

    insert = [call for call in executed if call[0].startswith("INSERT")]
    assert len(insert) == 1
    assert insert[0][1][1] == "alice"


def test_order_rejects_empty_payload(order_client):
    client, _ = order_client
    assert client.post("/orders", json={"user_id": "", "items": []}).status_code == 400
