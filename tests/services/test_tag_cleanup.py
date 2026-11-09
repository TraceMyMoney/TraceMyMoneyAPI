"""Tests for the one-time tag capitalization cleanup (tags-crud Step 2b)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text

from app.db.tables import expense_entry_tags
from app.services.tag_cleanup import capitalize_existing_tags


async def _insert_tag(db, user_id, name):
    """Insert straight into the table, bypassing the naming rule (that is the point: old data)."""
    tag_id = uuid.uuid4()
    await db.execute(
        expense_entry_tags.insert().values(
            id=tag_id, user_id=uuid.UUID(user_id), name=name, created_at=datetime.now(timezone.utc)
        )
    )
    await db.commit()
    return tag_id


async def _names(db, user_id):
    rows = await db.execute(select(expense_entry_tags.c.name).where(expense_entry_tags.c.user_id == uuid.UUID(user_id)))
    return sorted(r[0] for r in rows)


async def _second_user(client, test_db):
    payload = {"username": "seconduser", "email": "second@example.com", "password": "testpass123"}
    resp = await client.post("/register", json=payload)
    assert resp.status_code == 200, resp.text
    await test_db.execute(text("UPDATE users SET email_verified_at = now() WHERE username = 'seconduser'"))
    await test_db.commit()
    return resp.json()["user_id"]


async def test_dry_run_changes_nothing(registered_user, test_db):
    uid = registered_user["user_id"]
    await _insert_tag(test_db, uid, "food")
    report = await capitalize_existing_tags(test_db, apply=False)
    assert [(old, new) for _, old, new in report.changed] == [("food", "Food")]
    assert await _names(test_db, uid) == ["food"]


async def test_apply_capitalizes_and_keeps_acronyms_and_fine_names(registered_user, test_db):
    uid = registered_user["user_id"]
    for name in ("food", "EMI", "Travel", "rent and bills", "upi"):
        await _insert_tag(test_db, uid, name)
    report = await capitalize_existing_tags(test_db, apply=True)
    assert len(report.changed) == 3 and report.unchanged == 2 and report.skipped == []
    assert await _names(test_db, uid) == ["EMI", "Food", "Rent and bills", "Travel", "Upi"]


async def test_clash_is_skipped_and_reported_not_merged(registered_user, test_db):
    uid = registered_user["user_id"]
    lower_id = await _insert_tag(test_db, uid, "food")
    await _insert_tag(test_db, uid, "Food")
    report = await capitalize_existing_tags(test_db, apply=True)
    assert report.changed == []
    assert [(old, new) for _, old, new in report.skipped] == [("food", "Food")]
    assert await _names(test_db, uid) == ["Food", "food"]  # both kept, nothing merged
    still_there = await test_db.execute(select(expense_entry_tags.c.id).where(expense_entry_tags.c.id == lower_id))
    assert still_there.first() is not None


async def test_second_run_is_a_no_op(registered_user, test_db):
    uid = registered_user["user_id"]
    await _insert_tag(test_db, uid, "food")
    await capitalize_existing_tags(test_db, apply=True)
    again = await capitalize_existing_tags(test_db, apply=True)
    assert again.changed == [] and again.skipped == [] and again.unchanged == 1


async def test_other_users_tags_do_not_cause_clashes_and_are_handled_separately(client, registered_user, test_db):
    uid = registered_user["user_id"]
    other = await _second_user(client, test_db)
    await _insert_tag(test_db, uid, "food")
    await _insert_tag(test_db, other, "Food")  # same name, different user: no clash
    await _insert_tag(test_db, other, "gifts")
    report = await capitalize_existing_tags(test_db, apply=True)
    assert report.skipped == [] and len(report.changed) == 2
    assert await _names(test_db, uid) == ["Food"]
    assert await _names(test_db, other) == ["Food", "Gifts"]


async def test_extra_spaces_are_tidied_unless_they_clash(registered_user, test_db):
    uid = registered_user["user_id"]
    await _insert_tag(test_db, uid, "Rent  and bills")
    await _insert_tag(test_db, uid, "Gym  fees")
    await _insert_tag(test_db, uid, "Gym fees")
    report = await capitalize_existing_tags(test_db, apply=True)
    assert [(old, new) for _, old, new in report.changed] == [("Rent  and bills", "Rent and bills")]
    assert [(old, new) for _, old, new in report.skipped] == [("Gym  fees", "Gym fees")]
