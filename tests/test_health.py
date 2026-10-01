from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # 13.5.3: kod ve şema sürümü (ayrıntı `tests/test_version_guard.py`).
    assert set(body) == {"status", "schema", "code"}


def test_module_level_app_serves_health() -> None:
    # uvicorn ve Dockerfile `app.main:app` nesnesini yükler; fabrika ile aynı yolu sunmalı.
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
