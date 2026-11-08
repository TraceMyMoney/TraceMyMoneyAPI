"""SMS ingest webhook: token auth, parsing, dedupe, and the confirm flow."""

import pytest

from app.services.sms_parser import match_bank, parse_sms

HDFC_SMS = (
    "Sent Rs.40.00\nFrom HDFC Bank A/C *1234\nTo SWIGGY\nOn 06/11/26\nRef 612345678901\nNot You? Call 18002586161"
)


# ── parser ───────────────────────────────────────────────────────────────
def test_parses_upi_debit():
    p = parse_sms(HDFC_SMS)
    assert (p.amount, p.txn_type, p.merchant, p.account_hint, p.bank_hint) == (40.0, "debit", "Swiggy", "1234", "HDFC")
    assert (p.txn_date.year, p.txn_date.month, p.txn_date.day) == (2026, 11, 6)


def test_parses_credit_and_skips_balance():
    p = parse_sms("Rs 54000.00 credited to A/C XX1234 on 05-11-26 by NEFT from ACME PVT LTD. Avl Bal Rs 54118.00")
    assert (p.amount, p.txn_type, p.merchant) == (54000.0, "credit", "Acme Pvt Ltd")


def test_parses_sbi_style_without_currency_symbol():
    p = parse_sms("Dear UPI user A/C X1234 debited by 40.0 on date 06Nov26 trf to RAJESH KUMAR Refno 612345.")
    assert (p.amount, p.merchant) == (40.0, "Rajesh Kumar")


@pytest.mark.parametrize(
    "text",
    ["123456 is your OTP for txn of Rs 500. Do not share.", "Your Avl Bal Rs 1,234.00 in A/C XX1234.", "Hello there"],
)
def test_ignores_non_transactions(text):
    assert parse_sms(text) is None


def test_match_bank_prefers_longest_name_then_hint():
    banks = [{"id": "1", "name": "SBI"}, {"id": "2", "name": "SBI CREDIT CARD"}, {"id": "3", "name": "HDFC Savings"}]
    assert match_bank("spent on your SBI Credit Card at X", "SBI", banks) == "2"
    assert match_bank("Sent Rs 5 From HDFC Bank", "HDFC", banks) == "3"
    assert match_bank("Sent Rs 5 From ICICI Bank", "ICICI", banks) is None


# ── webhook ──────────────────────────────────────────────────────────────
async def _token(client, auth_headers):
    resp = await client.post("/ingest/token", headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()["token"]


async def test_webhook_requires_valid_token(client, auth_headers):
    assert (await client.post("/ingest/sms", json={"text": HDFC_SMS})).status_code == 401
    bad = await client.post("/ingest/sms", json={"text": HDFC_SMS}, headers={"X-Ingest-Token": "smm_nope"})
    assert bad.status_code == 401


async def test_sms_lands_in_pending_and_dedupes(client, auth_headers, created_bank):
    token = await _token(client, auth_headers)
    hdr = {"X-Ingest-Token": token}

    first = await client.post("/ingest/sms", json={"text": HDFC_SMS}, headers=hdr)
    assert first.status_code == 201
    txn = first.json()["transaction"]
    assert (txn["amount"], txn["type"], txn["merchant"], txn["date"]) == (40.0, "debit", "Swiggy", "2026-11-06")

    again = await client.post("/ingest/sms", json={"message": HDFC_SMS}, headers=hdr)  # alias + resend
    assert again.status_code == 200 and again.json()["status"] == "duplicate"

    ignored = await client.post("/ingest/sms", json={"text": "123456 is your OTP"}, headers=hdr)
    assert ignored.status_code == 200 and ignored.json()["status"] == "ignored"

    pending = (await client.get("/ingest/pending", headers=auth_headers)).json()["transactions"]
    assert len(pending) == 1


async def test_rotating_token_revokes_the_old_one(client, auth_headers):
    old = await _token(client, auth_headers)
    new = await _token(client, auth_headers)
    assert old != new
    assert (
        await client.post("/ingest/sms", json={"text": HDFC_SMS}, headers={"X-Ingest-Token": old})
    ).status_code == 401
    assert (
        await client.post("/ingest/sms", json={"text": HDFC_SMS}, headers={"X-Ingest-Token": new})
    ).status_code == 201
    status = (await client.get("/ingest/token", headers=auth_headers)).json()
    assert status["configured"] is True and status["last_used_at"] is not None


async def test_confirm_creates_then_appends_to_the_day(client, auth_headers, created_bank):
    hdr = {"X-Ingest-Token": await _token(client, auth_headers)}
    await client.post("/ingest/sms", json={"text": HDFC_SMS}, headers=hdr)
    second = "Rs 25.00 spent on HDFC Bank Card x1234 at CHAI POINT on 06/11/26."
    await client.post("/ingest/sms", json={"text": second}, headers=hdr)
    pending = (await client.get("/ingest/pending", headers=auth_headers)).json()["transactions"]
    assert len(pending) == 2

    # bank isn't matched ("Chase" is not in the SMS), so confirming without one is a 400
    no_bank = await client.post(f"/ingest/pending/{pending[0]['id']}/confirm", json={}, headers=auth_headers)
    assert no_bank.status_code == 400

    for item in pending:
        ok = await client.post(
            f"/ingest/pending/{item['id']}/confirm", json={"bank_id": created_bank["id"]}, headers=auth_headers
        )
        assert ok.status_code == 200 and ok.json()["status"] == "confirmed"

    # both entries share one expenses row for 6 Nov, totalling 65
    listing = (await client.get("/expenses/", params={"bank_id": created_bank["id"]}, headers=auth_headers)).json()
    assert len(listing["expenses"]) == 1
    assert listing["expenses"][0]["expense_total"] == 65.0
    assert not (await client.get("/ingest/pending", headers=auth_headers)).json()["transactions"]


async def test_credit_confirms_as_topup_and_reject_removes(client, auth_headers, created_bank):
    hdr = {"X-Ingest-Token": await _token(client, auth_headers)}
    await client.post(
        "/ingest/sms", json={"text": "Rs 500.00 credited to A/C XX1234 on 05-11-26 by UPI from ANITA"}, headers=hdr
    )
    await client.post(
        "/ingest/sms", json={"text": "Rs 99.00 debited from A/C XX1234 on 05-11-26 to NETFLIX"}, headers=hdr
    )
    items = (await client.get("/ingest/pending", headers=auth_headers)).json()["transactions"]
    credit = next(i for i in items if i["type"] == "credit")
    debit = next(i for i in items if i["type"] == "debit")

    assert (await client.delete(f"/ingest/pending/{debit['id']}", headers=auth_headers)).status_code == 200
    ok = await client.post(
        f"/ingest/pending/{credit['id']}/confirm", json={"bank_id": created_bank["id"]}, headers=auth_headers
    )
    assert ok.status_code == 200

    exp = (await client.get("/expenses/", params={"bank_id": created_bank["id"]}, headers=auth_headers)).json()[
        "expenses"
    ][0]
    assert exp["topup_expense_total"] == -500.0
    assert (await client.delete(f"/ingest/pending/{debit['id']}", headers=auth_headers)).status_code == 404
