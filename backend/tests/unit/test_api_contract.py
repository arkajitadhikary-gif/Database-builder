import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_liveness_contract() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "READY", "service": "backend"}


@pytest.mark.asyncio
async def test_session_guard_and_degraded_health(monkeypatch) -> None:
    import app.main as main_module

    monkeypatch.setattr(main_module.settings, "session_token", "test-token")
    async def unavailable_database() -> tuple[bool, str]:
        return False, "test database unavailable"

    monkeypatch.setattr(main_module, "check_database", unavailable_database)
    monkeypatch.setattr(
        main_module,
        "check_embedding_provider",
        lambda: (False, "test model unavailable"),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unauthorized = await client.get("/api/v1/health")
        authorized = await client.get(
            "/api/v1/health", headers={"Authorization": "Bearer test-token"}
        )
    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["status"] == "ERROR"
