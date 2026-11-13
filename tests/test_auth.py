import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "SecurePass1",
            "full_name": "New User",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["email"] == "newuser@example.com"


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "customer@test.com", "password": "Test@12345"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_login_invalid(client: AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "customer@test.com", "password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me(client: AsyncClient, auth_headers):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "customer@test.com"