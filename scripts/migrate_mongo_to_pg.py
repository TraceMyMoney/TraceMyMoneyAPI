"""
One-time MongoDB -> PostgreSQL data migration (PLAN.md Phase 5).

Connects live to the source MongoDB and the target PostgreSQL (rather than
parsing a mongodump BSON directory), using the same MONGODB_URL/DATABASE_URL
settings the app itself would use. Two passes, per PLAN.md:

  Pass 1 (independent collections): users, banks, expense_entry_tags.
          Each gets a fresh UUID; old ObjectId hex -> new UUID is recorded
          in-memory and persisted to `_migration_id_map` for auditability.

  Pass 2 (dependent collections): expenses (+ embedded entries + tag
          links), user_preferences. These resolve their foreign keys
          through the Pass 1 id maps.

Safety:
  - Refuses to run against a target `users` table that already has rows,
    unless --force is passed (this is a one-shot import into an empty DB).
  - --dry-run reads and reports counts from Mongo without writing anything.
  - Ends with reconciliation checks (row counts + balance sums) comparing
    source and target; any mismatch is printed clearly and the script exits
    non-zero.

Usage:
    uv run python scripts/migrate_mongo_to_pg.py --dry-run
    uv run python scripts/migrate_mongo_to_pg.py
    uv run python scripts/migrate_mongo_to_pg.py --force   # re-run into a non-empty DB
"""

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

# Allow running as `uv run python scripts/migrate_mongo_to_pg.py` (as documented
# below) in addition to `-m scripts.migrate_mongo_to_pg` - the former puts only
# scripts/ on sys.path, not the project root where `app` lives.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.db.tables import (
    metadata,
    users,
    banks,
    expense_entry_tags,
    expenses,
    expense_entries,
    expense_entry_tag_links,
    user_preferences,
    _migration_id_map,
)


def _utc(dt) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


class Migrator:
    def __init__(
        self, mongo_uri: str, mongo_db: str, pg_uri: str, batch_size: int, dry_run: bool, force: bool = False
    ):
        self.mongo = AsyncIOMotorClient(mongo_uri)[mongo_db]
        self.engine = create_async_engine(pg_uri)
        self.Session = async_sessionmaker(self.engine, expire_on_commit=False)
        self.batch_size = batch_size
        self.dry_run = dry_run
        self.force = force

        # old ObjectId hex -> new uuid.UUID, kept in memory for speed during
        # Pass 2 joins; also written to _migration_id_map for an audit trail.
        self.user_id_map: dict[str, uuid.UUID] = {}
        self.bank_id_map: dict[str, uuid.UUID] = {}
        self.tag_id_map: dict[str, uuid.UUID] = {}

        self.counts = {"users": 0, "banks": 0, "tags": 0, "expenses": 0, "entries": 0, "preferences": 0}
        # Documents intentionally skipped (missing required field, or an
        # orphaned user_id/bank_id reference to something that no longer
        # exists) - these are pre-existing data integrity gaps in the source
        # Mongo data, not something this migration invents or fixes. Tracked
        # so reconciliation can report an accurate expected count instead of
        # a false MISMATCH.
        self.skipped = {"users": 0, "banks": 0, "tags": 0, "expenses": 0, "preferences": 0}

    async def run(self) -> bool:
        if self.dry_run:
            return await self._dry_run_report()

        async with self.Session() as session:
            if not await self._check_target_empty(session):
                return False

        await self._migrate_users()
        await self._migrate_banks()
        await self._migrate_tags()
        await self._migrate_expenses()
        await self._migrate_user_preferences()

        return await self._reconcile()

    async def _check_target_empty(self, session) -> bool:
        result = await session.execute(select(func.count()).select_from(users))
        existing = result.scalar()
        if existing and not self.force:
            print(f"Refusing to run: target 'users' table already has {existing} row(s). Pass --force to override.")
            return False
        return True

    async def _dry_run_report(self) -> bool:
        print("DRY RUN - counting Mongo documents only, no writes:")
        for name, collection in (
            ("user", self.mongo.user),
            ("bank", self.mongo.bank),
            ("expense_entry_tag", self.mongo.expense_entry_tag),
            ("expense", self.mongo.expense),
            ("user_preference", self.mongo.user_preference),
        ):
            count = await collection.count_documents({})
            print(f"  {name}: {count}")
        entry_count = 0
        async for doc in self.mongo.expense.find({}, {"expenses": 1}):
            entry_count += len(doc.get("expenses", []))
        print(f"  expense entries (embedded): {entry_count}")
        return True

    async def _record_id_map(self, session, collection: str, mapping: dict[str, uuid.UUID]) -> None:
        if not mapping:
            return
        rows = [{"collection": collection, "old_id": old, "new_id": new} for old, new in mapping.items()]
        for i in range(0, len(rows), self.batch_size):
            await session.execute(_migration_id_map.insert(), rows[i : i + self.batch_size])

    async def _user_data_footprint(self, old_user_id: str) -> int:
        """How much data a user owns - used to pick a winner among duplicate accounts."""
        oid = ObjectId(old_user_id)
        banks_n = await self.mongo.bank.count_documents({"user_id": oid})
        tags_n = await self.mongo.expense_entry_tag.count_documents({"user_id": oid})
        expenses_n = await self.mongo.expense.count_documents({"user_id": oid})
        return banks_n + tags_n + expenses_n

    async def _migrate_users(self) -> None:
        print("Migrating users...")

        all_docs = await self.mongo.user.find({}).to_list(length=None)

        valid_docs = []
        for doc in all_docs:
            old_id = str(doc["_id"])
            if "password" not in doc or "username" not in doc or "email" not in doc:
                print(f"  WARNING: user {old_id} is missing a required field, skipping: {doc.get('email')!r}")
                self.skipped["users"] += 1
                continue
            valid_docs.append(doc)

        # Postgres enforces UNIQUE(email)/UNIQUE(username); Mongo never did.
        # For any duplicate group, keep whichever account actually owns data
        # (banks/tags/expenses) rather than just the first one seen - an
        # abandoned empty duplicate should lose to one with real data.
        by_email: dict[str, list] = {}
        for doc in valid_docs:
            by_email.setdefault(doc["email"], []).append(doc)

        docs_to_migrate = []
        for email, group in by_email.items():
            if len(group) == 1:
                docs_to_migrate.append(group[0])
                continue
            footprints = [(await self._user_data_footprint(str(d["_id"])), d) for d in group]
            footprints.sort(key=lambda fp: fp[0], reverse=True)
            winner = footprints[0][1]
            docs_to_migrate.append(winner)
            for _, loser in footprints[1:]:
                print(
                    f"  WARNING: duplicate email {email!r} - keeping user {winner['_id']} "
                    f"(data footprint {footprints[0][0]}), skipping {loser['_id']} (footprint "
                    f"{[fp for fp, d in footprints if d is loser][0]})"
                )
                self.skipped["users"] += 1

        # Same UNIQUE constraint applies to username; no duplicates exist as
        # of writing, but fail loudly rather than let Postgres reject the
        # whole batch with a cryptic error if that ever changes.
        seen_usernames: dict[str, object] = {}
        for doc in docs_to_migrate:
            if doc["username"] in seen_usernames:
                raise ValueError(
                    f"Duplicate username {doc['username']!r} between users "
                    f"{seen_usernames[doc['username']]} and {doc['_id']} - resolve manually before migrating."
                )
            seen_usernames[doc["username"]] = doc["_id"]

        async with self.Session() as session:
            batch = []
            for doc in docs_to_migrate:
                old_id = str(doc["_id"])
                new_id = uuid.uuid4()
                self.user_id_map[old_id] = new_id
                batch.append(
                    {
                        "id": new_id,
                        "username": doc["username"],
                        "email": doc["email"],
                        "password": doc["password"],
                        "is_subscribed_to_emails": doc.get("is_subscribed_to_emails", True),
                        "created_at": _utc(doc.get("created_at")),
                        "updated_at": _utc(doc.get("updated_at")),
                    }
                )
                self.counts["users"] += 1
                if len(batch) >= self.batch_size:
                    await session.execute(users.insert(), batch)
                    batch = []
            if batch:
                await session.execute(users.insert(), batch)
            await self._record_id_map(session, "user", self.user_id_map)
            await session.commit()
        print(f"  {self.counts['users']} users migrated")

    async def _migrate_banks(self) -> None:
        print("Migrating banks...")
        async with self.Session() as session:
            batch = []
            async for doc in self.mongo.bank.find({}):
                old_id = str(doc["_id"])
                old_user_id = str(doc["user_id"])
                new_user_id = self.user_id_map.get(old_user_id)
                if new_user_id is None:
                    print(f"  WARNING: bank {old_id} references unknown user {old_user_id}, skipping")
                    self.skipped["banks"] += 1
                    continue
                new_id = uuid.uuid4()
                self.bank_id_map[old_id] = new_id
                batch.append(
                    {
                        "id": new_id,
                        "user_id": new_user_id,
                        "name": doc["name"],
                        "initial_balance": doc.get("initial_balance", 0),
                        "current_balance": doc.get("current_balance", 0),
                        "total_disbursed_till_now": doc.get("total_disbursed_till_now", 0),
                        "created_at": _utc(doc.get("created_at")),
                        "updated_at": _utc(doc.get("updated_at")),
                    }
                )
                self.counts["banks"] += 1
                if len(batch) >= self.batch_size:
                    await session.execute(banks.insert(), batch)
                    batch = []
            if batch:
                await session.execute(banks.insert(), batch)
            await self._record_id_map(session, "bank", self.bank_id_map)
            await session.commit()
        print(f"  {self.counts['banks']} banks migrated")

    async def _migrate_tags(self) -> None:
        print("Migrating expense entry tags...")

        all_docs = await self.mongo.expense_entry_tag.find({}).to_list(length=None)

        valid_docs = []
        for doc in all_docs:
            old_id = str(doc["_id"])
            old_user_id = str(doc["user_id"])
            if old_user_id not in self.user_id_map:
                print(f"  WARNING: tag {old_id} references unknown user {old_user_id}, skipping")
                self.skipped["tags"] += 1
                continue
            valid_docs.append(doc)

        # Postgres enforces UNIQUE(user_id, name); Mongo's EntryTagService
        # checks for an existing name before inserting, but that check and
        # the insert aren't atomic, so a race can still produce duplicate
        # (user, name) tags (same bug family as the service's other
        # non-atomic writes - see PLAN.md). For any duplicate group, keep one
        # tag row but map EVERY original id in the group to its new UUID, so
        # expense entries that reference any of the duplicates still resolve
        # correctly - merging duplicates loses no user-visible information
        # since only the name is ever shown.
        by_key: dict[tuple[str, str], list] = {}
        for doc in valid_docs:
            by_key.setdefault((str(doc["user_id"]), doc["name"]), []).append(doc)

        docs_to_migrate = []
        for (old_user_id, name), group in by_key.items():
            group.sort(key=lambda d: d.get("created_at") or datetime.min)
            winner = group[0]
            new_id = uuid.uuid4()
            for doc in group:
                self.tag_id_map[str(doc["_id"])] = new_id
            docs_to_migrate.append((winner, new_id))
            if len(group) > 1:
                dupe_ids = [str(d["_id"]) for d in group[1:]]
                print(f"  WARNING: duplicate tag {name!r} for user {old_user_id} - merging {dupe_ids} into {winner['_id']}")
                self.skipped["tags"] += len(group) - 1

        async with self.Session() as session:
            batch = []
            for doc, new_id in docs_to_migrate:
                new_user_id = self.user_id_map[str(doc["user_id"])]
                batch.append(
                    {
                        "id": new_id,
                        "user_id": new_user_id,
                        "name": doc["name"],
                        "created_at": _utc(doc.get("created_at")),
                    }
                )
                self.counts["tags"] += 1
                if len(batch) >= self.batch_size:
                    await session.execute(expense_entry_tags.insert(), batch)
                    batch = []
            if batch:
                await session.execute(expense_entry_tags.insert(), batch)
            await self._record_id_map(session, "expense_entry_tag", self.tag_id_map)
            await session.commit()
        print(f"  {self.counts['tags']} tags migrated")

    async def _migrate_expenses(self) -> None:
        print("Migrating expenses and entries...")
        async with self.Session() as session:
            expense_id_map: dict[str, uuid.UUID] = {}
            expense_batch = []
            entry_batch = []
            link_batch = []

            async for doc in self.mongo.expense.find({}):
                old_expense_id = str(doc["_id"])
                old_user_id = str(doc["user_id"])
                old_bank_id = str(doc["bank"])
                new_user_id = self.user_id_map.get(old_user_id)
                new_bank_id = self.bank_id_map.get(old_bank_id)
                if new_user_id is None or new_bank_id is None:
                    print(f"  WARNING: expense {old_expense_id} references unknown user/bank, skipping")
                    self.skipped["expenses"] += 1
                    continue

                new_expense_id = uuid.uuid4()
                expense_id_map[old_expense_id] = new_expense_id
                created_at = _utc(doc.get("created_at"))

                expense_batch.append(
                    {
                        "id": new_expense_id,
                        "user_id": new_user_id,
                        "bank_id": new_bank_id,
                        "bank_name": doc.get("bank_name", ""),
                        "day": doc.get("day", ""),
                        "expense_total": doc.get("expense_total", 0),
                        "remaining_amount_till_now": doc.get("remaining_amount_till_now", 0),
                        "created_at": created_at,
                        "updated_at": _utc(doc.get("updated_at")),
                    }
                )

                for position, entry in enumerate(doc.get("expenses", [])):
                    new_entry_id = uuid.uuid4()
                    entry_batch.append(
                        {
                            "id": new_entry_id,
                            "ee_id": str(entry.get("ee_id")),
                            "expense_id": new_expense_id,
                            "amount": entry.get("amount", 0),
                            "description": entry.get("description", ""),
                            "expense_entry_type": entry.get("expense_entry_type", "expense"),
                            "position": position,
                            "created_at": _utc(entry.get("created_at")) if entry.get("created_at") else created_at,
                        }
                    )
                    self.counts["entries"] += 1

                    for old_tag_id in entry.get("entry_tags", []):
                        new_tag_id = self.tag_id_map.get(str(old_tag_id))
                        if new_tag_id is None:
                            continue  # dangling/invalid tag reference - dropped, matching PLAN.md note
                        link_batch.append({"expense_entry_id": new_entry_id, "tag_id": new_tag_id})

                self.counts["expenses"] += 1

                # Flush all three together, always in FK dependency order
                # (expenses -> expense_entries -> expense_entry_tag_links).
                # Flushing each list independently by its own size threshold
                # is wrong: link_batch grows fastest (multiple tags per
                # entry) and can hit batch_size while entry_batch - which it
                # has a foreign key to - hasn't been flushed yet, causing a
                # ForeignKeyViolationError on rows that exist in-memory but
                # not yet in Postgres.
                if (
                    len(expense_batch) >= self.batch_size
                    or len(entry_batch) >= self.batch_size
                    or len(link_batch) >= self.batch_size
                ):
                    if expense_batch:
                        await session.execute(expenses.insert(), expense_batch)
                        expense_batch = []
                    if entry_batch:
                        await session.execute(expense_entries.insert(), entry_batch)
                        entry_batch = []
                    if link_batch:
                        await session.execute(expense_entry_tag_links.insert(), link_batch)
                        link_batch = []

            if expense_batch:
                await session.execute(expenses.insert(), expense_batch)
            if entry_batch:
                await session.execute(expense_entries.insert(), entry_batch)
            if link_batch:
                await session.execute(expense_entry_tag_links.insert(), link_batch)

            await self._record_id_map(session, "expense", expense_id_map)
            await session.commit()
        print(f"  {self.counts['expenses']} expenses / {self.counts['entries']} entries migrated")

    async def _migrate_user_preferences(self) -> None:
        print("Migrating user preferences...")

        all_docs = await self.mongo.user_preference.find({}).to_list(length=None)

        valid_docs = []
        for doc in all_docs:
            old_user_id = str(doc["user_id"])
            if old_user_id not in self.user_id_map:
                print(f"  WARNING: preferences doc references unknown user {old_user_id}, skipping")
                self.skipped["preferences"] += 1
                continue
            valid_docs.append(doc)

        # Postgres enforces UNIQUE(user_id); Mongo's get_or_create_preferences
        # does a non-atomic find-then-insert (same bug family as the tag and
        # expense race conditions - see PLAN.md), so a user can end up with
        # more than one preferences document. Keep whichever was updated
        # most recently - that's the settings the user actually sees today.
        by_user: dict[str, list] = {}
        for doc in valid_docs:
            by_user.setdefault(str(doc["user_id"]), []).append(doc)

        docs_to_migrate = []
        for old_user_id, group in by_user.items():
            if len(group) > 1:
                group.sort(key=lambda d: d.get("updated_at") or d.get("created_at") or datetime.min, reverse=True)
                dupe_ids = [str(d["_id"]) for d in group[1:]]
                print(f"  WARNING: user {old_user_id} has {len(group)} preference docs - keeping most recently updated {group[0]['_id']}, skipping {dupe_ids}")
                self.skipped["preferences"] += len(group) - 1
            docs_to_migrate.append(group[0])

        async with self.Session() as session:
            batch = []
            for doc in docs_to_migrate:
                old_user_id = str(doc["user_id"])
                new_user_id = self.user_id_map[old_user_id]

                bank_order = [
                    self.bank_id_map[old_bid]
                    for old_bid in doc.get("banks_display_order", [])
                    if old_bid in self.bank_id_map
                ]

                batch.append(
                    {
                        "id": uuid.uuid4(),
                        "user_id": new_user_id,
                        "page_size": doc.get("page_size", 5),
                        "is_dark_mode": doc.get("is_dark_mode", False),
                        "privacy_mode_enabled": doc.get("privacy_mode_enabled") or False,
                        "banks_display_order": bank_order,
                        "created_at": _utc(doc.get("created_at")),
                        "updated_at": _utc(doc.get("updated_at")),
                    }
                )
                self.counts["preferences"] += 1

            if batch:
                await session.execute(user_preferences.insert(), batch)
            await session.commit()
        print(f"  {self.counts['preferences']} preference docs migrated")

    async def _reconcile(self) -> bool:
        print("\nReconciliation (expected = mongo count minus intentionally-skipped docs - see warnings above):")
        ok = True

        checks = [
            ("users", self.mongo.user, users, "users"),
            ("banks", self.mongo.bank, banks, "banks"),
            ("expense_entry_tags", self.mongo.expense_entry_tag, expense_entry_tags, "tags"),
            ("expenses", self.mongo.expense, expenses, "expenses"),
            ("user_preferences", self.mongo.user_preference, user_preferences, "preferences"),
        ]

        async with self.Session() as session:
            for label, mongo_collection, pg_table, skip_key in checks:
                mongo_count = await mongo_collection.count_documents({})
                expected = mongo_count - self.skipped[skip_key]
                pg_count = (await session.execute(select(func.count()).select_from(pg_table))).scalar()
                status = "OK" if expected == pg_count else "MISMATCH"
                if status == "MISMATCH":
                    ok = False
                skip_note = f" (skipped {self.skipped[skip_key]})" if self.skipped[skip_key] else ""
                print(f"  {label}: mongo={mongo_count}{skip_note} expected={expected} postgres={pg_count} [{status}]")

            mongo_entry_count = 0
            async for doc in self.mongo.expense.find({}, {"user_id": 1, "bank": 1, "expenses": 1}):
                # Entries belonging to a skipped (orphaned-reference) expense
                # were never migrated either - exclude them from the expected count.
                if str(doc["user_id"]) not in self.user_id_map or str(doc["bank"]) not in self.bank_id_map:
                    continue
                mongo_entry_count += len(doc.get("expenses", []))
            pg_entry_count = (await session.execute(select(func.count()).select_from(expense_entries))).scalar()
            status = "OK" if mongo_entry_count == pg_entry_count else "MISMATCH"
            if status == "MISMATCH":
                ok = False
            print(f"  expense_entries: expected={mongo_entry_count} postgres={pg_entry_count} [{status}]")

            mongo_balance_sum = 0.0
            async for doc in self.mongo.bank.find({}, {"user_id": 1, "current_balance": 1}):
                if str(doc["user_id"]) not in self.user_id_map:
                    continue
                mongo_balance_sum += doc.get("current_balance", 0)
            pg_balance_sum = (await session.execute(select(func.sum(banks.c.current_balance)))).scalar() or 0
            pg_balance_sum = float(pg_balance_sum)
            status = "OK" if abs(mongo_balance_sum - pg_balance_sum) < 0.01 else "MISMATCH"
            if status == "MISMATCH":
                ok = False
            print(f"  sum(current_balance): expected={mongo_balance_sum:.2f} postgres={pg_balance_sum:.2f} [{status}]")

        print("\n" + ("All reconciliation checks passed." if ok else "RECONCILIATION FAILED - see mismatches above."))
        return ok


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongo-uri", default=settings.MONGODB_URL)
    parser.add_argument("--mongo-db", default=settings.MONGODB_DB_NAME)
    parser.add_argument("--pg-uri", default=settings.DATABASE_URL)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true", help="Report Mongo counts only, write nothing.")
    parser.add_argument("--force", action="store_true", help="Run even if the target 'users' table isn't empty.")
    args = parser.parse_args()

    migrator = Migrator(args.mongo_uri, args.mongo_db, args.pg_uri, args.batch_size, args.dry_run, args.force)

    success = await migrator.run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
