"""SMS ingest webhook: token auth, parsing, dedupe, and the confirm flow."""

import pytest

from app.core.config import settings
from app.services import ingest_service
from app.services.sms_ai import AiVerdict, SmsExtraction, _to_parsed
from app.services.sms_parser import match_bank, parse_sms


@pytest.fixture(autouse=True)
def _no_real_ai(monkeypatch):
    """Tests never call a real model; the AI path is exercised with a stub."""
    monkeypatch.setattr(settings, "SMS_AI_PARSING", False)


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


SBI_SMS = (
    "Dear UPI user A/C X3690 debited by 20.00 on date 06Nov26 trf to Parking MM Refno 789732819990 "
    "If not u? call-1800111109 for other services-18001234-SBI"
)


def test_real_sbi_sms_parses_with_rules():
    p = parse_sms(SBI_SMS)
    assert (p.amount, p.txn_type, p.merchant, p.account_hint, p.bank_hint) == (
        20.0,
        "debit",
        "Parking MM",
        "3690",
        "SBI",
    )


def test_ai_answer_is_rejected_if_amount_is_not_in_the_sms():
    made_up = SmsExtraction(is_transaction=True, type="debit", amount=999.0, merchant="X")
    assert _to_parsed(made_up, SBI_SMS) is None
    ok = SmsExtraction(
        is_transaction=True,
        type="debit",
        amount=20.0,
        merchant="Parking MM",
        date="2026-11-06",
        account_last_digits="X3690",
        bank="sbi",
    )
    p = _to_parsed(ok, SBI_SMS)
    assert (p.amount, p.account_hint, p.bank_hint, p.txn_date.day) == (20.0, "3690", "SBI", 6)


async def test_webhook_uses_ai_result_then_falls_back(client, auth_headers, monkeypatch):
    token = (await client.post("/ingest/token", headers=auth_headers)).json()["token"]
    hdr = {"X-Ingest-Token": token}

    async def ai_ok(db, text, received_on):
        return AiVerdict(
            parsed=_to_parsed(
                SmsExtraction(is_transaction=True, type="debit", amount=20.0, merchant="Parking", date="2026-11-06"),
                text,
            )
        )

    monkeypatch.setattr(ingest_service, "extract_with_ai", ai_ok)
    first = await client.post("/ingest/sms", json={"text": SBI_SMS}, headers=hdr)
    assert first.status_code == 201
    assert first.json()["parsed_by"] == "ai" and first.json()["transaction"]["merchant"] == "Parking"

    async def ai_down(db, text, received_on):
        return None

    monkeypatch.setattr(ingest_service, "extract_with_ai", ai_down)
    second = await client.post("/ingest/sms", json={"text": SBI_SMS + " retry"}, headers=hdr)
    assert second.json()["parsed_by"] == "rules" and second.json()["transaction"]["merchant"] == "Parking MM"


async def test_ai_saying_not_a_transaction_is_ignored(client, auth_headers, monkeypatch):
    token = (await client.post("/ingest/token", headers=auth_headers)).json()["token"]

    async def ai_no(db, text, received_on):
        return AiVerdict(parsed=None)

    monkeypatch.setattr(ingest_service, "extract_with_ai", ai_no)
    resp = await client.post("/ingest/sms", json={"text": SBI_SMS}, headers={"X-Ingest-Token": token})
    assert resp.status_code == 200 and resp.json()["status"] == "ignored"


async def test_ai_call_caps_output_tokens(monkeypatch):
    """The admin's global max_tokens must not leak into the SMS call."""
    from app.core import llm as llm_module
    from app.services import sms_ai

    seen = {}

    class FakeStructured:
        async def ainvoke(self, messages, **kwargs):
            seen.update(kwargs)
            return SmsExtraction(is_transaction=True, type="debit", amount=20.0, merchant="Parking MM")

    class FakeLLM:
        def with_structured_output(self, schema):
            return FakeStructured()

    async def fake_get_llm(db):
        return FakeLLM()

    monkeypatch.setattr(settings, "SMS_AI_PARSING", True)
    monkeypatch.setattr(llm_module, "get_llm", fake_get_llm)
    verdict = await sms_ai.extract_with_ai(None, SBI_SMS, "2026-11-06")
    assert seen == {"max_tokens": sms_ai.MAX_OUTPUT_TOKENS}
    assert verdict.parsed.amount == 20.0


async def _bank(client, auth_headers, name):
    resp = await client.post(
        "/banks/create", json={"name": name, "initial_balance": 1000.0, "current_balance": 1000.0}, headers=auth_headers
    )
    assert resp.status_code == 200
    banks = (await client.get("/banks/", headers=auth_headers)).json()["banks"]
    return next(b for b in banks if b["name"] == name)


async def test_auto_add_when_account_is_recognised(client, auth_headers):
    sbi = await _bank(client, auth_headers, "SBI")
    hdr = {"X-Ingest-Token": await _token(client, auth_headers)}

    resp = await client.post("/ingest/sms", json={"text": SBI_SMS}, headers=hdr)
    assert resp.status_code == 201 and resp.json()["status"] == "added"

    listing = (await client.get("/expenses/", params={"bank_id": sbi["id"]}, headers=auth_headers)).json()
    assert listing["expenses"][0]["expense_total"] == 20.0
    assert not (await client.get("/ingest/pending", headers=auth_headers)).json()["transactions"]
    # re-sending the same SMS must not add it twice
    again = await client.post("/ingest/sms", json={"text": SBI_SMS}, headers=hdr)
    assert again.json()["status"] == "duplicate"


async def test_auto_add_off_or_unknown_account_waits_for_review(client, auth_headers):
    await _bank(client, auth_headers, "SBI")
    await _token(client, auth_headers)
    token = (await client.post("/ingest/token", headers=auth_headers)).json()["token"]
    hdr = {"X-Ingest-Token": token}

    off = await client.patch("/ingest/settings", json={"auto_add": False}, headers=auth_headers)
    assert off.status_code == 200
    assert (await client.get("/ingest/token", headers=auth_headers)).json()["auto_add"] is False
    assert (await client.post("/ingest/sms", json={"text": SBI_SMS}, headers=hdr)).json()["status"] == "stored"

    await client.patch("/ingest/settings", json={"auto_add": True}, headers=auth_headers)
    unknown = "Rs 99.00 debited from A/C XX1234 on 06-11-26 to NETFLIX"  # no account name in the text
    assert (await client.post("/ingest/sms", json={"text": unknown}, headers=hdr)).json()["status"] == "stored"


async def test_settings_needs_a_token_first(client, auth_headers):
    resp = await client.patch("/ingest/settings", json={"auto_add": False}, headers=auth_headers)
    assert resp.status_code == 404


async def test_added_sms_follows_the_normal_expense_rules(client, auth_headers):
    """Same-day SMS share one row, the balance goes down, other users' banks are refused."""
    sbi = await _bank(client, auth_headers, "SBI")  # opening balance 1000
    hdr = {"X-Ingest-Token": await _token(client, auth_headers)}
    first = "Rs.20.00 spent on your SBI Credit Card at CHAI on 06/11/26 Ref 1"
    second = "Rs.30.00 spent on your SBI Credit Card at VADA on 06/11/26 Ref 2"
    refund = "Rs 5.00 credited to SBI A/C XX3690 on 06-11-26 by UPI from SHOP Ref 3"
    for sms in (first, second, refund):
        assert (await client.post("/ingest/sms", json={"text": sms}, headers=hdr)).json()["status"] == "added"

    listing = (await client.get("/expenses/", params={"bank_id": sbi["id"]}, headers=auth_headers)).json()
    assert len(listing["expenses"]) == 1  # one row for the day, not three
    day = listing["expenses"][0]
    assert len(day["expenses"]) == 3 and day["expense_total"] == 50.0
    bank = next(b for b in (await client.get("/banks/", headers=auth_headers)).json()["banks"] if b["id"] == sbi["id"])
    assert bank["current_balance"] == 1000.0 - 20.0 - 30.0 + 5.0

    other = {"username": "other_person", "email": "o@example.com", "password": "testpass123"}
    await client.post("/register", json=other)
    other_login = (await client.post("/login", json={"username": "other_person", "password": "testpass123"})).json()
    other_headers = {"Authorization": other_login["token"]}
    ot = (await client.post("/ingest/token", headers=other_headers)).json()["token"]
    await client.patch("/ingest/settings", json={"auto_add": False}, headers=other_headers)
    stored = await client.post("/ingest/sms", json={"text": "Rs 9.00 debited from A/C XX1 to X on 06-11-26"}, headers={"X-Ingest-Token": ot})
    pending_id = stored.json()["transaction"]["id"]
    stolen = await client.post(f"/ingest/pending/{pending_id}/confirm", json={"bank_id": sbi["id"]}, headers=other_headers)
    assert stolen.status_code == 400
