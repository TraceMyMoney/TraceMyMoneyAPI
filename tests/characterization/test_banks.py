"""Characterization tests for /banks."""


async def test_create_bank(client, auth_headers):
    resp = await client.post(
        "/banks/create",
        json={"name": "Chase", "initial_balance": 5000.0, "current_balance": 5000.0},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"success": "Bank object saved successfully"}


async def test_get_banks_empty(client, auth_headers):
    resp = await client.get("/banks/", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"banks": []}


async def test_get_banks_after_create(client, auth_headers, created_bank):
    resp = await client.get("/banks/", headers=auth_headers)
    assert resp.status_code == 200
    banks = resp.json()["banks"]
    assert len(banks) == 1
    bank = banks[0]
    assert bank["name"] == "Chase"
    assert bank["initial_balance"] == 5000.0
    assert bank["current_balance"] == 5000.0
    assert bank["total_disbursed_till_now"] == 0.0
    assert "id" in bank
    assert "created_at" in bank


async def test_get_banks_filter_by_id(client, auth_headers, created_bank):
    resp = await client.get("/banks/", params={"id": created_bank["id"]}, headers=auth_headers)
    assert resp.status_code == 200
    banks = resp.json()["banks"]
    assert len(banks) == 1
    assert banks[0]["id"] == created_bank["id"]


async def test_get_banks_filter_by_name(client, auth_headers, created_bank):
    resp = await client.get("/banks/", params={"name": "Chase"}, headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["banks"]) == 1


async def test_create_bank_rejects_non_positive_balance(client, auth_headers):
    resp = await client.post(
        "/banks/create",
        json={"name": "Chase", "initial_balance": 0, "current_balance": 0},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_delete_bank(client, auth_headers, created_bank):
    resp = await client.delete("/banks/delete", params={"bank_id": created_bank["id"]}, headers=auth_headers)
    assert resp.status_code == 204

    banks_resp = await client.get("/banks/", headers=auth_headers)
    assert banks_resp.json()["banks"] == []


async def test_delete_bank_unknown_id(client, auth_headers):
    resp = await client.delete("/banks/delete", params={"bank_id": "507f1f77bcf86cd799439011"}, headers=auth_headers)
    assert resp.status_code == 400


async def test_delete_bank_cascades_to_expenses(client, auth_headers, created_bank):
    """
    FIXED in Phase 3 (was bug #2 in PLAN.md): under Mongo, BankService.delete_bank
    deleted from `db.expenses` (plural) while ExpenseService wrote to `db.expense`
    (singular), so expenses belonging to a deleted bank were silently orphaned.
    Now `expenses.bank_id` has `ON DELETE CASCADE`, so deleting a bank correctly
    removes its expenses (and their entries/tag links) too.
    """
    await client.post(
        "/expenses/create",
        json={
            "bank_id": created_bank["id"],
            "expenses": [{"amount": 50.0, "description": "test", "entry_tags": [], "type": "expense"}],
        },
        headers=auth_headers,
    )

    await client.delete("/banks/delete", params={"bank_id": created_bank["id"]}, headers=auth_headers)

    expenses_resp = await client.get("/expenses/", params={"bank_id": created_bank["id"]}, headers=auth_headers)
    assert expenses_resp.json()["total_expenses"] == 0
