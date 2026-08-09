from app.api.routes.health import health
from app.main import app


def test_health():
    response = health()

    assert response.model_dump() == {"status": "ok"}
    assert "/health" in app.openapi()["paths"]
