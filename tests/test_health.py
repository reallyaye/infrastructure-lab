from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_endpoint_exposes_http_counter() -> None:
    client = TestClient(app)
    client.get("/health")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "http_requests_total" in response.text
