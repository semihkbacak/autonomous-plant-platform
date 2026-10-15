
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_dashboard_page_is_available():
    response = client.get("/solar/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "GES Monitoring Dashboard" in response.text
    assert 'id="bars"' in response.text


def test_dashboard_does_not_accept_post():
    response = client.post("/solar/dashboard")

    assert response.status_code == 405


def test_existing_hes_health_is_preserved():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
