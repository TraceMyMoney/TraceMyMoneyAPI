"""Characterization tests for /expenses.

These pin down ExpenseService's aggregation-pipeline-based reads and
non-atomic multi-write mutations exactly as they currently behave on Mongo,
bugs included (see PLAN.md).
"""

import pytest


@pytest.fixture
def expense_payload():
    return {
        "bank_id": None,  # filled in by tests using created_bank
        "expenses": [
            {"amount": 50.0, "description": "Groceries", "entry_tags": [], "type": "expense"},
            {"amount": -20.0, "description": "Refund", "entry_tags": [], "type": "topup"},
        ],
        "created_at": "01/01/2026 00:00",
    }


async def test_create_expense(client, auth_headers, created_bank, expense_payload):
    expense_payload["bank_id"] = created_bank["id"]
    resp = await client.post("/expenses/create", json=expense_payload, headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] == "Docuement created successfully"
    assert "_id" in body


async def test_create_expense_updates_bank_balance(client, auth_headers, created_bank, expense_payload):
    expense_payload["bank_id"] = created_bank["id"]
    await client.post("/expenses/create", json=expense_payload, headers=auth_headers)

    banks_resp = await client.get("/banks/", headers=auth_headers)
    bank = banks_resp.json()["banks"][0]
    # net total = 50 + (-20) = 30; current_balance decreases by net total
    assert bank["current_balance"] == 5000.0 - 30.0
    assert bank["total_disbursed_till_now"] == 30.0


async def test_create_duplicate_expense_same_day_rejected(client, auth_headers, created_bank, expense_payload):
    expense_payload["bank_id"] = created_bank["id"]
    await client.post("/expenses/create", json=expense_payload, headers=auth_headers)

    resp = await client.post("/expenses/create", json=expense_payload, headers=auth_headers)
    assert resp.status_code == 400
    assert "cannot replicate" in resp.json()["detail"]


async def test_create_expense_unknown_bank_rejected(client, auth_headers, expense_payload):
    expense_payload["bank_id"] = "507f1f77bcf86cd799439011"
    resp = await client.post("/expenses/create", json=expense_payload, headers=auth_headers)
    assert resp.status_code == 400


async def test_get_expenses_list(client, auth_headers, created_bank, expense_payload):
    expense_payload["bank_id"] = created_bank["id"]
    await client.post("/expenses/create", json=expense_payload, headers=auth_headers)

    resp = await client.get("/expenses/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_expenses"] == 1
    assert body["non_topup_total"] == 50.0
    assert body["topup_total"] == -20.0

    expense = body["expenses"][0]
    assert expense["bank_name"] == "Chase"
    assert len(expense["expenses"]) == 2
    assert expense["expense_total"] == 50.0
    assert expense["remaining_amount_till_now"] == 5000.0 - 30.0


async def test_get_expenses_empty(client, auth_headers):
    resp = await client.get("/expenses/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"expenses": [], "total_expenses": 0, "non_topup_total": 0, "topup_total": 0}


async def test_get_expenses_filtered_by_bank(client, auth_headers, created_bank, expense_payload):
    expense_payload["bank_id"] = created_bank["id"]
    await client.post("/expenses/create", json=expense_payload, headers=auth_headers)

    resp = await client.get("/expenses/", params={"bank_id": created_bank["id"]}, headers=auth_headers)
    assert resp.json()["total_expenses"] == 1

    # A well-formed but non-existent UUID (not the old 24-hex Mongo ObjectId
    # format, which is no longer a valid ID shape under Postgres).
    resp2 = await client.get(
        "/expenses/", params={"bank_id": "00000000-0000-0000-0000-000000000000"}, headers=auth_headers
    )
    assert resp2.json()["total_expenses"] == 0


async def test_remaining_amount_recalculated_for_earlier_expense(client, auth_headers, created_bank):
    """
    create_expense back-dates remaining_amount_till_now for all later
    expenses when an earlier-dated expense is inserted afterwards.
    """
    bank_id = created_bank["id"]

    await client.post(
        "/expenses/create",
        json={
            "bank_id": bank_id,
            "expenses": [{"amount": 100.0, "description": "later", "entry_tags": [], "type": "expense"}],
            "created_at": "05/01/2026 00:00",
        },
        headers=auth_headers,
    )
    # remaining after "later" expense: 5000 - 100 = 4900

    await client.post(
        "/expenses/create",
        json={
            "bank_id": bank_id,
            "expenses": [{"amount": 50.0, "description": "earlier", "entry_tags": [], "type": "expense"}],
            "created_at": "01/01/2026 00:00",
        },
        headers=auth_headers,
    )
    # remaining after "earlier" expense: 5000 - 50 = 4950
    # "later" expense's remaining should now be decremented by 50 -> 4850

    # PRE-EXISTING QUIRK: remaining_amount_till_now is seeded from the bank's
    # CURRENT balance (already decremented by the "later" expense inserted
    # first), not from a chronological running total. So both expenses end
    # up with the same remaining_amount_till_now (4850.0) instead of the
    # earlier expense reflecting a higher balance than the later one.
    resp = await client.get("/expenses/", headers=auth_headers)
    expenses_by_amount = {e["expense_total"]: e for e in resp.json()["expenses"]}
    assert expenses_by_amount[50.0]["remaining_amount_till_now"] == 4850.0
    assert expenses_by_amount[100.0]["remaining_amount_till_now"] == 4850.0


async def test_add_expense_entry(client, auth_headers, created_bank, expense_payload):
    expense_payload["bank_id"] = created_bank["id"]
    create_resp = await client.post("/expenses/create", json=expense_payload, headers=auth_headers)
    expense_id = create_resp.json()["_id"]

    resp = await client.patch(
        f"/expenses/add-entry?id={expense_id}",
        json={"entries": [{"amount": 10.0, "description": "extra", "entry_tags": [], "type": "expense"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json() == {"success": "Added expense successfully"}

    list_resp = await client.get("/expenses/", headers=auth_headers)
    expense = list_resp.json()["expenses"][0]
    assert len(expense["expenses"]) == 3
    assert expense["expense_total"] == 60.0


async def test_add_expense_entry_unknown_id(client, auth_headers):
    resp = await client.patch(
        "/expenses/add-entry?id=507f1f77bcf86cd799439011",
        json={"entries": [{"amount": 10.0, "description": "extra", "entry_tags": [], "type": "expense"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_update_expense_entry(client, auth_headers, created_bank, expense_payload):
    expense_payload["bank_id"] = created_bank["id"]
    create_resp = await client.post("/expenses/create", json=expense_payload, headers=auth_headers)
    expense_id = create_resp.json()["_id"]

    list_resp = await client.get("/expenses/", headers=auth_headers)
    entry_id = list_resp.json()["expenses"][0]["expenses"][0]["ee_id"]

    resp = await client.patch(
        "/expenses/update-entry",
        json={"expense_id": expense_id, "entry_id": entry_id, "updated_description": "Updated"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()["data"]
    assert body["description"] == "Updated"
    assert body["entry_id"] == entry_id


async def test_update_expense_entry_missing_fields_rejected(client, auth_headers):
    """
    FIXED in Phase 3 (was bug #6 in PLAN.md): the endpoint's guard clause
    used to read `entry_data.selected_tags`, a field that doesn't exist on
    `ExpenseEntryUpdate` (the real field is `entry_tags`), raising an
    unhandled AttributeError -> 500. Now correctly returns 400.
    """
    resp = await client.patch(
        "/expenses/update-entry",
        json={"expense_id": "00000000-0000-0000-0000-000000000000", "entry_id": "ee_x"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "tags or description" in resp.json()["detail"]


async def test_delete_expense_entry(client, auth_headers, created_bank, expense_payload):
    expense_payload["bank_id"] = created_bank["id"]
    create_resp = await client.post("/expenses/create", json=expense_payload, headers=auth_headers)
    expense_id = create_resp.json()["_id"]

    list_resp = await client.get("/expenses/", headers=auth_headers)
    entry_id = list_resp.json()["expenses"][0]["expenses"][0]["ee_id"]

    resp = await client.delete(
        "/expenses/delete-entry", params={"id": expense_id, "ee_id": entry_id}, headers=auth_headers
    )
    assert resp.status_code == 204

    list_resp2 = await client.get("/expenses/", headers=auth_headers)
    expense = list_resp2.json()["expenses"][0]
    assert len(expense["expenses"]) == 1


async def test_delete_last_expense_entry_deletes_whole_expense(client, auth_headers, created_bank):
    create_resp = await client.post(
        "/expenses/create",
        json={
            "bank_id": created_bank["id"],
            "expenses": [{"amount": 50.0, "description": "only", "entry_tags": [], "type": "expense"}],
        },
        headers=auth_headers,
    )
    expense_id = create_resp.json()["_id"]

    list_resp = await client.get("/expenses/", headers=auth_headers)
    entry_id = list_resp.json()["expenses"][0]["expenses"][0]["ee_id"]

    resp = await client.delete(
        "/expenses/delete-entry", params={"id": expense_id, "ee_id": entry_id}, headers=auth_headers
    )
    assert resp.status_code == 204

    list_resp2 = await client.get("/expenses/", headers=auth_headers)
    assert list_resp2.json()["total_expenses"] == 0


async def test_delete_expense(client, auth_headers, created_bank, expense_payload):
    expense_payload["bank_id"] = created_bank["id"]
    create_resp = await client.post("/expenses/create", json=expense_payload, headers=auth_headers)
    expense_id = create_resp.json()["_id"]

    resp = await client.delete("/expenses/delete", params={"id": expense_id}, headers=auth_headers)
    assert resp.status_code == 204

    list_resp = await client.get("/expenses/", headers=auth_headers)
    assert list_resp.json()["total_expenses"] == 0


async def test_delete_expense_restores_bank_balance(client, auth_headers, created_bank, expense_payload):
    expense_payload["bank_id"] = created_bank["id"]
    create_resp = await client.post("/expenses/create", json=expense_payload, headers=auth_headers)
    expense_id = create_resp.json()["_id"]

    await client.delete("/expenses/delete", params={"id": expense_id}, headers=auth_headers)

    banks_resp = await client.get("/banks/", headers=auth_headers)
    bank = banks_resp.json()["banks"][0]
    assert bank["current_balance"] == 5000.0
    assert bank["total_disbursed_till_now"] == 0.0


async def test_delete_expense_unknown_id(client, auth_headers):
    resp = await client.delete("/expenses/delete", params={"id": "507f1f77bcf86cd799439011"}, headers=auth_headers)
    assert resp.status_code == 404


async def test_create_bulk_expenses(client, auth_headers, created_bank):
    bank_id = created_bank["id"]
    payload = [
        {
            "bank_id": bank_id,
            "expenses": [{"amount": 10.0, "description": "d1", "entry_tags": [], "type": "expense"}],
            "created_at": "01/01/2026 00:00",
        },
        {
            "bank_id": bank_id,
            "expenses": [{"amount": 20.0, "description": "d2", "entry_tags": [], "type": "expense"}],
            "created_at": "02/01/2026 00:00",
        },
    ]
    resp = await client.post("/expenses/create-bulk", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] == "Docuements inserted successfully"
    assert len(body["ids"]) == 2

    list_resp = await client.get("/expenses/", headers=auth_headers)
    assert list_resp.json()["total_expenses"] == 2


async def test_graph_data_is_always_empty_bug(client, auth_headers, created_bank):
    """
    PRE-EXISTING BUG (tracked in PLAN.md as bug #1): get_aggregated_data
    matches `{"user_id": user_id}` (a plain string) against documents where
    `user_id` is stored as an ObjectId, and also filters on a `bank_id` field
    that doesn't exist on the Expense document (the field is `bank`). Both
    make the initial $match stage match nothing, so /expenses/graph-data
    always returns an empty result regardless of data present. This test
    pins down that CURRENT (broken) behavior; the Postgres rewrite must FIX
    this so graph data is actually returned.
    """
    await client.post(
        "/expenses/create",
        json={
            "bank_id": created_bank["id"],
            "expenses": [
                {"amount": 50.0, "description": "d", "entry_tags": ["sometag"], "type": "expense"}
            ],
        },
        headers=auth_headers,
    )

    resp = await client.get("/expenses/graph-data", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"aggregated_data": {}}
