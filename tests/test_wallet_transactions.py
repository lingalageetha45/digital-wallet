import pytest
from httpx import AsyncClient
from decimal import Decimal


@pytest.mark.asyncio
async def test_create_wallet_and_deposit(client: AsyncClient, auth_headers):
    # Create wallet
    resp = await client.post(
        "/api/wallets",
        json={"currency": "INR", "name": "Main"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    wallet_id = resp.json()["data"]["id"]

    # Deposit
    resp = await client.post(
        f"/api/wallets/{wallet_id}/deposits",
        json={"amount": "5000.00", "description": "Initial"},
        headers={**auth_headers, "Idempotency-Key": "dep-key-1"},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["status"] == "COMPLETED"

    # Check balance
    resp = await client.get(f"/api/wallets/{wallet_id}", headers=auth_headers)
    assert Decimal(resp.json()["data"]["available_balance"]) == Decimal("5000.00")


@pytest.mark.asyncio
async def test_transfer_and_insufficient_balance(client: AsyncClient, auth_headers):
    # Create two wallets for same user (simpler for test)
    r1 = await client.post("/api/wallets", json={"currency": "INR"}, headers=auth_headers)
    w1 = r1.json()["data"]["id"]
    r2 = await client.post("/api/wallets", json={"currency": "INR"}, headers=auth_headers)
    w2 = r2.json()["data"]["id"]

    await client.post(
        f"/api/wallets/{w1}/deposits",
        json={"amount": "1000.00"},
        headers=auth_headers,
    )

    # Successful transfer
    resp = await client.post(
        "/api/transfers",
        json={
            "sender_wallet_id": w1,
            "receiver_wallet_id": w2,
            "amount": "300.00",
        },
        headers={**auth_headers, "Idempotency-Key": "trf-1"},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["status"] == "COMPLETED"

    # Insufficient
    resp = await client.post(
        "/api/transfers",
        json={
            "sender_wallet_id": w1,
            "receiver_wallet_id": w2,
            "amount": "900.00",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INSUFFICIENT_BALANCE"


@pytest.mark.asyncio
async def test_idempotency(client: AsyncClient, auth_headers):
    r = await client.post("/api/wallets", json={"currency": "INR"}, headers=auth_headers)
    wid = r.json()["data"]["id"]
    key = "unique-idem-key-xyz"

    resp1 = await client.post(
        f"/api/wallets/{wid}/deposits",
        json={"amount": "100.00"},
        headers={**auth_headers, "Idempotency-Key": key},
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        f"/api/wallets/{wid}/deposits",
        json={"amount": "100.00"},
        headers={**auth_headers, "Idempotency-Key": key},
    )
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "DUPLICATE_IDEMPOTENCY_KEY"