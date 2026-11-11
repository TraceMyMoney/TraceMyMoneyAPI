"""Daily expense limit: the preference and the per-row `day_total` the UI compares it with."""

import pytest


async def _set_limit(client, auth_headers, value):
    return await client.patch("/user-preferences/update", json={"daily_expense_limit": value}, headers=auth_headers)


async def _limit(client, auth_headers):
    return (await client.get("/user-preferences/", headers=auth_headers)).json()["daily_expense_limit"]


async def _second_bank(client, auth_headers):
    await client.post(
        "/banks/create",
        json={"name": "Cash", "initial_balance": 1000.0, "current_balance": 1000.0},
        headers=auth_headers,
    )
    banks = (await client.get("/banks/", headers=auth_headers)).json()["banks"]
    return next(b for b in banks if b["name"] == "Cash")


async def _add(client, auth_headers, bank_id, created_at, amounts):
    payload = {
        "bank_id": bank_id,
        "expenses": [{"amount": a, "description": "x", "entry_tags": [], "type": "expense"} for a in amounts],
        "created_at": created_at,
    }
    resp = await client.post("/expenses/create", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text


async def test_limit_defaults_to_none_and_can_be_set_and_cleared(client, auth_headers):
    assert await _limit(client, auth_headers) is None

    assert (await _set_limit(client, auth_headers, 150)).status_code == 200
    assert await _limit(client, auth_headers) == 150.0

    assert (await _set_limit(client, auth_headers, 99.5)).status_code == 200
    assert await _limit(client, auth_headers) == 99.5

    # explicit null clears
    assert (await _set_limit(client, auth_headers, None)).status_code == 200
    assert await _limit(client, auth_headers) is None


async def test_other_updates_do_not_touch_the_limit(client, auth_headers):
    await _set_limit(client, auth_headers, 150)
    await client.patch("/user-preferences/update", json={"page_size": 20}, headers=auth_headers)
    assert await _limit(client, auth_headers) == 150.0


@pytest.mark.parametrize("bad", [0, -5, "abc", 10_000_001, 1.234])
async def test_invalid_limit_is_422(client, auth_headers, bad):
    await _set_limit(client, auth_headers, 150)
    resp = await _set_limit(client, auth_headers, bad)
    assert resp.status_code == 422
    assert await _limit(client, auth_headers) == 150.0


async def test_day_total_sums_all_banks_and_ignores_credits(client, auth_headers, created_bank):
    cash = await _second_bank(client, auth_headers)
    await _add(client, auth_headers, created_bank["id"], "05/03/2026 00:00", [100.0, -30.0])
    await _add(client, auth_headers, cash["id"], "05/03/2026 00:00", [60.0])
    await _add(client, auth_headers, created_bank["id"], "06/03/2026 00:00", [40.0])

    body = (await client.get("/expenses/", headers=auth_headers)).json()
    by_day = {}
    for e in body["expenses"]:
        by_day.setdefault(e["created_at"][:10], []).append(e["day_total"])
    assert by_day["05/03/2026"] == [160.0, 160.0]
    assert by_day["06/03/2026"] == [40.0]


async def test_day_total_correct_when_day_rows_are_on_different_pages(client, auth_headers, created_bank):
    cash = await _second_bank(client, auth_headers)
    await _add(client, auth_headers, created_bank["id"], "05/03/2026 00:00", [100.0])
    await _add(client, auth_headers, cash["id"], "05/03/2026 00:00", [60.0])

    resp = await client.get("/expenses/?per_page=1&page_number=1", headers=auth_headers)
    rows = resp.json()["expenses"]
    assert len(rows) == 1
    assert rows[0]["day_total"] == 160.0


async def test_day_total_ignores_search_filters_and_is_per_user(client, auth_headers, created_bank, test_db):
    from sqlalchemy import text

    cash = await _second_bank(client, auth_headers)
    await _add(client, auth_headers, created_bank["id"], "05/03/2026 00:00", [100.0])
    await _add(client, auth_headers, cash["id"], "05/03/2026 00:00", [60.0])

    # another user's spending on the same day must never be counted
    other = {"username": "otheruser", "email": "other@example.com", "password": "testpass123"}
    await client.post("/register", json=other)
    await test_db.execute(text("UPDATE users SET email_verified_at = now() WHERE username = 'otheruser'"))
    await test_db.commit()
    token = (await client.post("/login", json={"username": "otheruser", "password": "testpass123"})).json()["token"]
    other_headers = {"Authorization": f"Bearer {token}"}
    await client.post(
        "/banks/create", json={"name": "Z", "initial_balance": 500.0, "current_balance": 500.0}, headers=other_headers
    )
    other_bank = (await client.get("/banks/", headers=other_headers)).json()["banks"][0]
    await _add(client, other_headers, other_bank["id"], "05/03/2026 00:00", [999.0])

    rows = (await client.get(f"/expenses/?bank_id={created_bank['id']}", headers=auth_headers)).json()["expenses"]
    assert len(rows) == 1
    assert rows[0]["day_total"] == 160.0
