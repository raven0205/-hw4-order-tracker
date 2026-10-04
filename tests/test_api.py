from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "orders.db")
    with TestClient(main.app) as test_client:
        yield test_client


def test_health_and_seeded_orders(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    orders = client.get("/api/orders").json()
    assert len(orders) == 3
    assert {order["priority"] for order in orders} == {"standard", "express"}


def test_express_order_delivery_date_crosses_month_end(client):
    response = client.get("/api/orders/express-1002")

    assert response.status_code == 200
    placed_at = datetime.fromisoformat(response.json()["created_at"])
    assert response.json()["estimated_delivery"] == (
        placed_at + timedelta(days=2)
    ).date().isoformat()


def test_create_and_update_order(client):
    response = client.post(
        "/api/orders",
        json={"customer": "Taylor", "item": "Mug", "priority": "standard"},
    )
    assert response.status_code == 201
    order_id = response.json()["id"]
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "received"
    updated = client.patch(f"/api/orders/{order_id}", json={"status": "shipped"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "shipped"


def test_missing_order(client):
    assert client.get("/api/orders/missing").status_code == 404


def test_lookup_request_metric_includes_route_and_status(client, monkeypatch):
    records = []

    class Counter:
        def add(self, value, attributes):
            records.append((value, attributes))

    monkeypatch.setattr(main, "lookup_requests", Counter())

    assert client.get("/api/orders/standard-1001").status_code == 200
    assert client.get("/api/orders/missing").status_code == 404
    assert records == [
        (1, {"http.route": "/api/orders/{order_id}", "http.response.status_code": 200}),
        (1, {"http.route": "/api/orders/{order_id}", "http.response.status_code": 404}),
    ]


def test_lookup_request_metric_counts_unhandled_errors(client, monkeypatch):
    records = []

    class Counter:
        def add(self, value, attributes):
            records.append((value, attributes))

    def fail_to_connect():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "lookup_requests", Counter())
    monkeypatch.setattr(main, "connect", fail_to_connect)

    with pytest.raises(RuntimeError):
        client.get("/api/orders/standard-1001")

    assert records == [
        (1, {"http.route": "/api/orders/{order_id}", "http.response.status_code": 500})
    ]
