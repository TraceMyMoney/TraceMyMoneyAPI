import base64
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import banks, ingest_tokens, pending_transactions
from app.schemas.expense import ExpenseCreate
from app.schemas.expense_entry import ExpenseEntryCreate
from app.services.expense_service import ExpenseService
from app.services.sms_ai import extract_with_ai
from app.services.sms_parser import match_bank, parse_sms

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "smm_"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _text_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.lower().split()).encode()).hexdigest()


def _parse_received_at(value: str | None) -> datetime:
    if value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _serialize(row) -> dict:
    return {
        "id": str(row["id"]),
        "amount": float(row["amount"]),
        "type": row["txn_type"],
        "merchant": row["merchant"],
        "description": row["description"],
        "date": row["txn_date"].date().isoformat(),
        "account_hint": row["account_hint"],
        "bank_id": str(row["bank_id"]) if row["bank_id"] else None,
        "status": row["status"],
        "raw_text": row["raw_text"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


class IngestService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── token ────────────────────────────────────────────────────────────
    async def create_token(self, user_id: str) -> str:
        """Create (or rotate) the user's webhook token. Returns the plaintext once."""
        # 16 lowercase letters/digits (80 bits): short enough to read and
        # type, far too large to guess.
        token = TOKEN_PREFIX + base64.b32encode(secrets.token_bytes(10)).decode().lower()
        now = datetime.now(timezone.utc)
        stmt = pg_insert(ingest_tokens).values(
            id=uuid.uuid4(), user_id=uuid.UUID(user_id), token_hash=hash_token(token), created_at=now
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ingest_tokens.c.user_id],
            set_={"token_hash": hash_token(token), "created_at": now, "last_used_at": None},
        )
        await self.db.execute(stmt)
        await self.db.commit()
        return token

    async def revoke_token(self, user_id: str) -> bool:
        res = await self.db.execute(ingest_tokens.delete().where(ingest_tokens.c.user_id == uuid.UUID(user_id)))
        await self.db.commit()
        return res.rowcount > 0

    async def token_status(self, user_id: str) -> dict:
        row = (
            (await self.db.execute(select(ingest_tokens).where(ingest_tokens.c.user_id == uuid.UUID(user_id))))
            .mappings()
            .first()
        )
        if not row:
            return {"configured": False, "auto_add": True, "created_at": None, "last_used_at": None}
        return {
            "configured": True,
            "auto_add": row["auto_add"],
            "created_at": row["created_at"].isoformat(),
            "last_used_at": row["last_used_at"].isoformat() if row["last_used_at"] else None,
        }

    async def set_auto_add(self, user_id: str, enabled: bool) -> bool:
        res = await self.db.execute(
            update(ingest_tokens).where(ingest_tokens.c.user_id == uuid.UUID(user_id)).values(auto_add=enabled)
        )
        await self.db.commit()
        return res.rowcount > 0

    async def user_id_for_token(self, token: str) -> str | None:
        """Resolve a webhook token to its user id and note when it was used."""
        row = (
            (await self.db.execute(select(ingest_tokens).where(ingest_tokens.c.token_hash == hash_token(token))))
            .mappings()
            .first()
        )
        if not row:
            return None
        await self.db.execute(
            update(ingest_tokens).where(ingest_tokens.c.id == row["id"]).values(last_used_at=datetime.now(timezone.utc))
        )
        await self.db.commit()
        return str(row["user_id"])

    # ── webhook ──────────────────────────────────────────────────────────
    async def ingest_sms(self, user_id: str, text: str, received_at: str | None) -> dict:
        parsed_by = "ai"
        verdict = await extract_with_ai(self.db, text, _parse_received_at(received_at).date().isoformat())
        if verdict is not None:
            parsed = verdict.parsed
        else:
            # AI unavailable (no key, rate limit, timeout) or its answer didn't
            # check out: fall back to the fixed patterns.
            parsed_by = "rules"
            parsed = parse_sms(text)
        if parsed is None:
            return {"status": "ignored", "reason": "Not a debit or credit transaction message"}

        uid = uuid.UUID(user_id)
        user_banks = [
            {"id": str(r["id"]), "name": r["name"]}
            for r in (await self.db.execute(select(banks.c.id, banks.c.name).where(banks.c.user_id == uid)))
            .mappings()
            .all()
        ]
        bank_id = match_bank(text, parsed.bank_hint, user_banks)
        # No account named in the SMS -> bank_id stays None and the transaction waits in
        # the review list for the user to choose the account.
        txn_date = parsed.txn_date or _parse_received_at(received_at).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )
        description = (parsed.merchant or ("Credit" if parsed.txn_type == "credit" else "UPI / card payment"))[:200]

        values = dict(
            id=uuid.uuid4(),
            user_id=uid,
            raw_text=text,
            amount=parsed.amount,
            txn_type=parsed.txn_type,
            merchant=parsed.merchant,
            description=description,
            txn_date=txn_date.replace(tzinfo=timezone.utc),
            account_hint=parsed.account_hint,
            bank_id=uuid.UUID(bank_id) if bank_id else None,
            status="pending",
            dedupe_hash=_text_hash(text),
        )
        stmt = (
            pg_insert(pending_transactions)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_pending_transactions_user_hash")
            .returning(pending_transactions.c.id)
        )
        inserted = (await self.db.execute(stmt)).first()
        await self.db.commit()
        auto_add = (
            await self.db.execute(select(ingest_tokens.c.auto_add).where(ingest_tokens.c.user_id == uid))
        ).scalar()

        if inserted is None:
            # Already received. If it is still waiting in the review list (it came in
            # before auto-add existed, or before the account was recognised) and
            # auto-add can handle it now, add it instead of ignoring the re-send.
            existing = (
                (
                    await self.db.execute(
                        select(pending_transactions).where(
                            pending_transactions.c.user_id == uid,
                            pending_transactions.c.dedupe_hash == values["dedupe_hash"],
                        )
                    )
                )
                .mappings()
                .first()
            )
            target = (str(existing["bank_id"]) if existing and existing["bank_id"] else None) or bank_id
            if existing and existing["status"] == "pending" and auto_add and target:
                try:
                    added = await self.confirm(user_id, str(existing["id"]), target, None, [], None)
                    transaction = _serialize(existing)
                    transaction["status"] = "confirmed"
                    return {
                        "status": "added",
                        "parsed_by": parsed_by,
                        "expense_id": added["expense_id"],
                        "transaction": transaction,
                    }
                except Exception:
                    logger.exception("Auto-add of a waiting transaction failed")
            return {"status": "duplicate", "reason": "This message was already received"}

        row = (
            (await self.db.execute(select(pending_transactions).where(pending_transactions.c.id == inserted.id)))
            .mappings()
            .one()
        )
        transaction = _serialize(row)

        # Auto-add: the SMS clearly names one of the user's accounts, so skip the
        # review list. Anything unclear (or with the switch off) stays pending.
        if auto_add and bank_id:
            try:
                added = await self.confirm(user_id, transaction["id"], None, None, [], None)
                transaction["status"] = "confirmed"
                return {
                    "status": "added",
                    "parsed_by": parsed_by,
                    "expense_id": added["expense_id"],
                    "transaction": transaction,
                }
            except Exception:
                logger.exception("Auto-add failed; leaving the transaction in the review list")
        return {"status": "stored", "parsed_by": parsed_by, "transaction": transaction}

    # ── inbox ────────────────────────────────────────────────────────────
    async def list_pending(self, user_id: str, status: str = "pending") -> list[dict]:
        rows = (
            (
                await self.db.execute(
                    select(pending_transactions)
                    .where(
                        pending_transactions.c.user_id == uuid.UUID(user_id), pending_transactions.c.status == status
                    )
                    .order_by(pending_transactions.c.txn_date.desc(), pending_transactions.c.created_at.desc())
                )
            )
            .mappings()
            .all()
        )
        return [_serialize(r) for r in rows]

    async def _get_pending(self, user_id: str, pending_id: str):
        try:
            pid = uuid.UUID(pending_id)
        except ValueError:
            return None
        return (
            (
                await self.db.execute(
                    select(pending_transactions).where(
                        pending_transactions.c.id == pid, pending_transactions.c.user_id == uuid.UUID(user_id)
                    )
                )
            )
            .mappings()
            .first()
        )

    async def reject(self, user_id: str, pending_id: str) -> bool:
        row = await self._get_pending(user_id, pending_id)
        if not row or row["status"] != "pending":
            return False
        await self.db.execute(
            update(pending_transactions).where(pending_transactions.c.id == row["id"]).values(status="rejected")
        )
        await self.db.commit()
        return True

    async def confirm(
        self,
        user_id: str,
        pending_id: str,
        bank_id: str | None,
        description: str | None,
        entry_tags: list[str],
        amount: float | None,
    ) -> dict:
        """Turn a pending transaction into a real expense entry (debits are
        positive, credits negative, same as the add-expense form)."""
        row = await self._get_pending(user_id, pending_id)
        if not row or row["status"] != "pending":
            raise LookupError("Pending transaction not found")

        target_bank = bank_id or (str(row["bank_id"]) if row["bank_id"] else None)
        if not target_bank:
            raise ValueError("Choose which account this transaction belongs to")
        try:
            owned = (
                await self.db.execute(
                    select(banks.c.id).where(banks.c.id == uuid.UUID(target_bank), banks.c.user_id == uuid.UUID(user_id))
                )
            ).first()
        except ValueError:
            owned = None
        if not owned:
            raise ValueError("That account was not found")

        value = float(amount if amount is not None else row["amount"])
        signed = value if row["txn_type"] == "debit" else -value
        entry = ExpenseEntryCreate(
            amount=signed, description=(description or row["description"] or "")[:200], entry_tags=entry_tags
        )
        d = row["txn_date"]
        date_str = f"{d.day}/{d.month}/{d.year} 00:00"

        expenses = ExpenseService(self.db)
        existing_id = await expenses.find_expense_id_for_day(user_id, target_bank, date_str)
        if existing_id:
            await expenses.add_expense_entries(user_id, existing_id, [entry])
            expense_id = existing_id
        else:
            created = await expenses.create_expense(
                user_id, ExpenseCreate(bank_id=target_bank, expenses=[entry], created_at=date_str)
            )
            expense_id = created.id

        await self.db.execute(
            update(pending_transactions)
            .where(pending_transactions.c.id == row["id"])
            .values(status="confirmed", bank_id=uuid.UUID(target_bank))
        )
        await self.db.commit()
        return {"status": "confirmed", "expense_id": expense_id}
