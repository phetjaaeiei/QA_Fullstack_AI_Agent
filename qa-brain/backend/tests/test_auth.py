import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_login_returns_token(test_user):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/login", data={
            "username": "qa@extosoft.com",
            "password": "testpassword"
        })
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(test_user):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/auth/login", data={
            "username": "qa@extosoft.com",
            "password": "wrongpassword"
        })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_without_token_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/stories/PROJ-123/test-cases")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_returns_new_token(auth_token, test_user):
    import asyncio
    await asyncio.sleep(1)  # Ensure new expiry so token differs
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/auth/refresh",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["access_token"] != auth_token  # New token issued
