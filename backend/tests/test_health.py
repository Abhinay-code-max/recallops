from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    # Hits real Hindsight Cloud (a cheap alist_memories ping) -- per this project's rule
    # of verifying against the live API rather than mocking it away. Used as a context
    # manager so the app's lifespan runs and the Hindsight client's aiohttp session stays
    # bound to one event loop for the whole test.
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["memory"] in ("ok", "slow", "down")
