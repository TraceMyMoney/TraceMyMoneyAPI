import uuid
from typing import List, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy import select, and_, or_, true, false, case, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.tables import expenses, expense_entries, expense_entry_tag_links, expense_entry_tags, banks
from app.models.expense import ExpenseModel
from app.models.expense_entry import ExpenseEntryModel
from app.schemas.expense import ExpenseCreate
from app.schemas.expense_entry import ExpenseEntryCreate, ExpenseEntryUpdate
from app.schemas.common import AdvancedSearchParams
from app.utils.date_utils import parse_date_string, to_utc_aware
from app.services.user_service import is_valid_id


def _valid_uuids(ids: List[str]) -> List[uuid.UUID]:
    return [uuid.UUID(i) for i in ids if is_valid_id(i)]


class ExpenseService:
    """Service for expense-related business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _link_tags(self, entry_pk: uuid.UUID, entry_tag_ids: List[str]) -> None:
        """Best-effort tag linking: silently skips IDs that aren't valid UUIDs
        (matches the Mongo-era behavior of never validating entry_tags)."""
        tag_uuids = _valid_uuids(entry_tag_ids)
        if tag_uuids:
            await self.db.execute(
                expense_entry_tag_links.insert(),
                [{"expense_entry_id": entry_pk, "tag_id": tid} for tid in tag_uuids],
            )

    async def find_expense_id_for_day(
        self, user_id: str, bank_id: str, date_str: Optional[str] = None
    ) -> Optional[str]:
        """Look up the existing expenses row (if any) for this bank+day, so
        callers can append to it via add_expense_entries instead of hitting
        create_expense's one-row-per-bank-per-day guard. date_str uses the
        same format as ExpenseCreate.created_at; omit it for today."""
        uid = uuid.UUID(user_id)
        bid = uuid.UUID(bank_id)
        created_at = to_utc_aware(parse_date_string(date_str)) if date_str else datetime.now(timezone.utc)
        row = (
            await self.db.execute(
                select(expenses.c.id).where(
                    expenses.c.bank_id == bid, expenses.c.user_id == uid, expenses.c.created_at == created_at
                )
            )
        ).first()
        return str(row.id) if row else None

    async def create_expense(self, user_id: str, expense_data: ExpenseCreate) -> ExpenseModel:
        """Create a new expense with entries."""
        uid = uuid.UUID(user_id)
        bank_id = uuid.UUID(expense_data.bank_id)

        bank_row = (await self.db.execute(select(banks).where(banks.c.id == bank_id))).mappings().first()
        if not bank_row:
            raise ValueError("Bank not found for the corresponding id")

        if expense_data.created_at:
            created_at = to_utc_aware(parse_date_string(expense_data.created_at))
        else:
            created_at = datetime.now(timezone.utc)

        existing = (
            await self.db.execute(
                select(expenses.c.id).where(
                    expenses.c.bank_id == bank_id, expenses.c.user_id == uid, expenses.c.created_at == created_at
                )
            )
        ).first()
        if existing:
            raise ValueError("You cannot replicate the expense for the same day")

        prev_expense = (
            await self.db.execute(
                select(expenses.c.remaining_amount_till_now)
                .where(expenses.c.bank_id == bank_id, expenses.c.user_id == uid, expenses.c.created_at < created_at)
                .order_by(expenses.c.created_at.desc())
                .limit(1)
            )
        ).first()

        after_expense_ids = [
            r.id
            for r in (
                await self.db.execute(
                    select(expenses.c.id).where(
                        expenses.c.bank_id == bank_id,
                        expenses.c.user_id == uid,
                        expenses.c.created_at > created_at,
                    )
                )
            ).all()
        ]

        entries: List[ExpenseEntryModel] = []
        total_amount = 0.0
        for entry_data in expense_data.expenses:
            ee_id = f"ee_{uuid.uuid4().hex[:12]}"
            entry = ExpenseEntryModel(
                ee_id=ee_id,
                amount=entry_data.amount,
                description=entry_data.description,
                entry_tags=entry_data.entry_tags,
                expense_entry_type=entry_data.type,
                created_at=created_at,
            )
            entries.append(entry)
            total_amount += entry.amount

        remaining_balance = (
            float(prev_expense.remaining_amount_till_now) if prev_expense else float(bank_row["current_balance"])
        ) - total_amount

        new_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        await self.db.execute(
            expenses.insert().values(
                id=new_id,
                user_id=uid,
                bank_id=bank_id,
                bank_name=bank_row["name"],
                day=created_at.strftime("%A"),
                expense_total=total_amount,
                remaining_amount_till_now=remaining_balance,
                created_at=created_at,
                updated_at=now,
            )
        )

        for position, entry in enumerate(entries):
            entry_pk = uuid.uuid4()
            await self.db.execute(
                expense_entries.insert().values(
                    id=entry_pk,
                    ee_id=entry.ee_id,
                    expense_id=new_id,
                    amount=entry.amount,
                    description=entry.description,
                    expense_entry_type=entry.expense_entry_type.value,
                    position=position,
                    created_at=created_at,
                )
            )
            await self._link_tags(entry_pk, entry.entry_tags)

        await self.db.execute(
            banks.update()
            .where(banks.c.id == bank_id)
            .values(
                current_balance=banks.c.current_balance - total_amount,
                total_disbursed_till_now=banks.c.total_disbursed_till_now + total_amount,
                updated_at=now,
            )
        )

        if after_expense_ids:
            await self.db.execute(
                expenses.update()
                .where(expenses.c.id.in_(after_expense_ids))
                .values(remaining_amount_till_now=expenses.c.remaining_amount_till_now - total_amount)
            )

        await self.db.commit()

        return ExpenseModel(
            id=str(new_id),
            user_id=user_id,
            bank=str(bank_id),
            bank_name=bank_row["name"],
            day=created_at.strftime("%A"),
            expenses=entries,
            expense_total=total_amount,
            remaining_amount_till_now=remaining_balance,
            created_at=created_at,
            updated_at=now,
        )

    async def get_expenses(
        self, user_id: str, params: AdvancedSearchParams
    ) -> Tuple[List[dict], int, float, float]:
        """
        Get expenses with advanced search and pagination.
        Returns: (expenses, total_count, non_topup_total, topup_total)
        """
        uid = uuid.UUID(user_id)
        e, ee, links = expenses, expense_entries, expense_entry_tag_links

        other_conditions = []

        if params.advanced_search:
            if params.search_by_tags:
                tag_uuids = _valid_uuids(params.search_by_tags)
                other_conditions.append(
                    ee.c.id.in_(select(links.c.expense_entry_id).where(links.c.tag_id.in_(tag_uuids)))
                    if tag_uuids
                    else false()
                )

            if params.search_by_keyword:
                other_conditions.append(ee.c.description.ilike(f"%{params.search_by_keyword}%"))

            if params.search_by_bank_ids:
                bank_uuids = _valid_uuids(params.search_by_bank_ids)
                other_conditions.append(e.c.bank_id.in_(bank_uuids) if bank_uuids else false())

            if params.search_by_daterange:
                date_cond = [e.c.created_at >= to_utc_aware(parse_date_string(params.search_by_daterange.start_date))]
                if params.search_by_daterange.end_date:
                    date_cond.append(
                        e.c.created_at <= to_utc_aware(parse_date_string(params.search_by_daterange.end_date))
                    )
                other_conditions.append(and_(*date_cond))
        else:
            if params.bank_id and is_valid_id(params.bank_id):
                other_conditions.append(e.c.bank_id == uuid.UUID(params.bank_id))

        combiner = or_ if params.operator == "or" else and_
        # The current user's own data is always required, regardless of
        # `operator` - this is NOT part of the and/or-combined group. (Fixes
        # a cross-user data leak present in the original Mongo aggregation,
        # which OR'd the user_id match together with the other filters, so
        # `operator=or` with e.g. a matching bank_id could return other
        # users' expenses too. See PLAN.md.)
        entry_filter = combiner(*other_conditions) if other_conditions else true()

        # Pagination and totals are computed in SQL against just the matching
        # expense ids, instead of pulling every matching expense+entry row
        # into Python on every request (that previously meant a full
        # join+load of a user's entire expense history just to show 5 rows -
        # the dominant cost on initial page load for accounts with real
        # history).
        id_stmt = (
            select(e.c.id, e.c.created_at)
            .distinct()
            .select_from(e.join(ee, ee.c.expense_id == e.c.id))
            .where(e.c.user_id == uid, entry_filter)
            .order_by(e.c.created_at.desc())
        )

        total_count = (
            await self.db.execute(select(func.count()).select_from(id_stmt.subquery()))
        ).scalar_one()

        skip = (params.page_number - 1) * params.per_page
        page_ids = [
            r.id
            for r in (await self.db.execute(id_stmt.limit(params.per_page).offset(skip))).all()
        ]

        agg_row = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(case((ee.c.amount > 0, ee.c.amount), else_=0)), 0).label(
                        "non_topup_total"
                    ),
                    func.coalesce(func.sum(case((ee.c.amount < 0, ee.c.amount), else_=0)), 0).label(
                        "topup_total"
                    ),
                )
                .select_from(e.join(ee, ee.c.expense_id == e.c.id))
                .where(e.c.user_id == uid, entry_filter)
            )
        ).one()
        non_topup_total = float(agg_row.non_topup_total)
        topup_total = float(agg_row.topup_total)

        grouped: dict = {}
        if page_ids:
            stmt = (
                select(
                    e.c.id.label("expense_id"),
                    e.c.user_id.label("expense_user_id"),
                    e.c.bank_name,
                    e.c.day,
                    e.c.remaining_amount_till_now,
                    e.c.created_at.label("expense_created_at"),
                    ee.c.id.label("entry_pk"),
                    ee.c.ee_id,
                    ee.c.amount,
                    ee.c.description,
                    ee.c.expense_entry_type,
                    ee.c.created_at.label("entry_created_at"),
                )
                .select_from(e.join(ee, ee.c.expense_id == e.c.id))
                .where(e.c.id.in_(page_ids), entry_filter)
                .order_by(e.c.created_at.desc(), ee.c.position.asc())
            )

            rows = (await self.db.execute(stmt)).mappings().all()

            entry_pks = [r["entry_pk"] for r in rows]
            tag_map: dict = {}
            if entry_pks:
                link_rows = (
                    await self.db.execute(
                        select(links.c.expense_entry_id, links.c.tag_id).where(
                            links.c.expense_entry_id.in_(entry_pks)
                        )
                    )
                ).all()
                for link in link_rows:
                    tag_map.setdefault(link.expense_entry_id, []).append(str(link.tag_id))

            for r in rows:
                eid = r["expense_id"]
                if eid not in grouped:
                    grouped[eid] = {
                        "_id": str(eid),
                        "id": str(eid),
                        "user_id": str(r["expense_user_id"]),
                        "bank_name": r["bank_name"],
                        "day": r["day"],
                        "remaining_amount_till_now": float(r["remaining_amount_till_now"]),
                        "created_at": r["expense_created_at"],
                        "expense_total": 0.0,
                        "topup_expense_total": 0.0,
                        "expenses": [],
                    }
                amount = float(r["amount"])
                if amount > 0:
                    grouped[eid]["expense_total"] += amount
                else:
                    grouped[eid]["topup_expense_total"] += amount
                grouped[eid]["expenses"].append(
                    {
                        "ee_id": r["ee_id"],
                        "amount": amount,
                        "description": r["description"],
                        "entry_tags": tag_map.get(r["entry_pk"], []),
                        "expense_entry_type": r["expense_entry_type"],
                        "created_at": r["entry_created_at"],
                    }
                )

        paginated_expenses = list(grouped.values())

        return paginated_expenses, total_count, non_topup_total, topup_total

    async def get_expense_by_id(self, user_id: str, expense_id: str) -> Optional[ExpenseModel]:
        """Get a single expense by ID."""
        if not is_valid_id(expense_id):
            return None

        uid = uuid.UUID(user_id)
        eid = uuid.UUID(expense_id)

        expense_row = (
            await self.db.execute(select(expenses).where(expenses.c.id == eid, expenses.c.user_id == uid))
        ).mappings().first()
        if not expense_row:
            return None

        entry_rows = (
            await self.db.execute(
                select(expense_entries).where(expense_entries.c.expense_id == eid).order_by(expense_entries.c.position)
            )
        ).mappings().all()

        entry_pks = [r["id"] for r in entry_rows]
        tag_map: dict = {}
        if entry_pks:
            link_rows = (
                await self.db.execute(
                    select(expense_entry_tag_links.c.expense_entry_id, expense_entry_tag_links.c.tag_id).where(
                        expense_entry_tag_links.c.expense_entry_id.in_(entry_pks)
                    )
                )
            ).all()
            for link in link_rows:
                tag_map.setdefault(link.expense_entry_id, []).append(str(link.tag_id))

        entry_models = [
            ExpenseEntryModel(
                ee_id=r["ee_id"],
                amount=float(r["amount"]),
                description=r["description"],
                entry_tags=tag_map.get(r["id"], []),
                expense_entry_type=r["expense_entry_type"],
                created_at=r["created_at"],
            )
            for r in entry_rows
        ]

        return ExpenseModel(
            id=str(expense_row["id"]),
            user_id=str(expense_row["user_id"]),
            bank=str(expense_row["bank_id"]),
            bank_name=expense_row["bank_name"],
            day=expense_row["day"],
            expenses=entry_models,
            expense_total=float(expense_row["expense_total"]),
            remaining_amount_till_now=float(expense_row["remaining_amount_till_now"]),
            created_at=expense_row["created_at"],
            updated_at=expense_row["updated_at"],
        )

    async def add_expense_entries(
        self, user_id: str, expense_id: str, entries: List[ExpenseEntryCreate]
    ) -> Optional[dict]:
        """Add new entries to an existing expense."""
        if not is_valid_id(expense_id):
            return None

        uid = uuid.UUID(user_id)
        eid = uuid.UUID(expense_id)

        expense_row = (
            await self.db.execute(select(expenses).where(expenses.c.id == eid, expenses.c.user_id == uid))
        ).mappings().first()
        if not expense_row:
            return None

        after_expense_ids = [
            r.id
            for r in (
                await self.db.execute(
                    select(expenses.c.id).where(
                        expenses.c.bank_id == expense_row["bank_id"],
                        expenses.c.user_id == uid,
                        expenses.c.created_at > expense_row["created_at"],
                    )
                )
            ).all()
        ]

        existing_count = (
            await self.db.execute(
                select(func.count()).select_from(expense_entries).where(expense_entries.c.expense_id == eid)
            )
        ).scalar()

        total_added = 0.0
        for offset, entry_data in enumerate(entries):
            ee_id = f"ee_{uuid.uuid4().hex[:12]}"
            entry_pk = uuid.uuid4()
            await self.db.execute(
                expense_entries.insert().values(
                    id=entry_pk,
                    ee_id=ee_id,
                    expense_id=eid,
                    amount=entry_data.amount,
                    description=entry_data.description,
                    expense_entry_type=entry_data.type.value,
                    position=existing_count + offset,
                    created_at=expense_row["created_at"],
                )
            )
            await self._link_tags(entry_pk, entry_data.entry_tags)
            total_added += entry_data.amount

        remaining_balance = float(expense_row["remaining_amount_till_now"]) - total_added
        now = datetime.now(timezone.utc)

        await self.db.execute(
            expenses.update()
            .where(expenses.c.id == eid)
            .values(
                expense_total=expenses.c.expense_total + total_added,
                remaining_amount_till_now=remaining_balance,
                updated_at=now,
            )
        )

        await self.db.execute(
            banks.update()
            .where(banks.c.id == expense_row["bank_id"])
            .values(
                current_balance=banks.c.current_balance - total_added,
                total_disbursed_till_now=banks.c.total_disbursed_till_now + total_added,
            )
        )

        if after_expense_ids:
            await self.db.execute(
                expenses.update()
                .where(expenses.c.id.in_(after_expense_ids))
                .values(remaining_amount_till_now=expenses.c.remaining_amount_till_now - total_added)
            )

        await self.db.commit()
        return {"id": str(eid)}

    async def update_expense_entry(self, user_id: str, update_data: ExpenseEntryUpdate) -> Optional[dict]:
        """Update a specific expense entry."""
        if not is_valid_id(update_data.expense_id):
            return None

        uid = uuid.UUID(user_id)
        eid = uuid.UUID(update_data.expense_id)

        row = (
            await self.db.execute(
                select(expense_entries.c.id, expense_entries.c.description)
                .select_from(expense_entries.join(expenses, expenses.c.id == expense_entries.c.expense_id))
                .where(
                    expenses.c.id == eid,
                    expenses.c.user_id == uid,
                    expense_entries.c.ee_id == update_data.entry_id,
                )
            )
        ).first()

        if not row:
            return None

        entry_pk = row.id
        final_description = row.description

        if update_data.updated_description is not None:
            final_description = update_data.updated_description
            await self.db.execute(
                expense_entries.update().where(expense_entries.c.id == entry_pk).values(description=final_description)
            )

        if update_data.entry_tags is not None:
            await self.db.execute(
                expense_entry_tag_links.delete().where(expense_entry_tag_links.c.expense_entry_id == entry_pk)
            )
            await self._link_tags(entry_pk, update_data.entry_tags)

        await self.db.commit()

        tag_rows = (
            await self.db.execute(
                select(expense_entry_tag_links.c.tag_id).where(expense_entry_tag_links.c.expense_entry_id == entry_pk)
            )
        ).all()
        selected_tags = [str(t.tag_id) for t in tag_rows]

        return {
            "expense_id": str(eid),
            "entry_id": update_data.entry_id,
            "selected_tags": selected_tags,
            "description": final_description,
        }

    async def delete_expense_entry(self, user_id: str, expense_id: str, entry_id: str) -> bool:
        """Delete a specific expense entry."""
        if not is_valid_id(expense_id):
            return False

        uid = uuid.UUID(user_id)
        eid = uuid.UUID(expense_id)

        expense_row = (
            await self.db.execute(select(expenses).where(expenses.c.id == eid, expenses.c.user_id == uid))
        ).mappings().first()
        if not expense_row:
            return False

        entry_row = (
            await self.db.execute(
                select(expense_entries).where(expense_entries.c.expense_id == eid, expense_entries.c.ee_id == entry_id)
            )
        ).mappings().first()
        if not entry_row:
            return False

        after_expense_ids = [
            r.id
            for r in (
                await self.db.execute(
                    select(expenses.c.id).where(
                        expenses.c.bank_id == expense_row["bank_id"],
                        expenses.c.user_id == uid,
                        expenses.c.created_at > expense_row["created_at"],
                    )
                )
            ).all()
        ]

        entry_count = (
            await self.db.execute(
                select(func.count()).select_from(expense_entries).where(expense_entries.c.expense_id == eid)
            )
        ).scalar()

        amount = float(entry_row["amount"])

        if entry_count == 1:
            await self.db.execute(expenses.delete().where(expenses.c.id == eid))
        else:
            remaining_balance = float(expense_row["remaining_amount_till_now"]) + amount
            await self.db.execute(expense_entries.delete().where(expense_entries.c.id == entry_row["id"]))
            # NOTE: expense_total is intentionally NOT decremented here - this
            # matches the original Mongo behavior, which also never adjusted
            # it on a partial entry delete (only full-expense delete reads
            # expense_total). Preserved as-is per PLAN.md migration scope.
            await self.db.execute(
                expenses.update()
                .where(expenses.c.id == eid)
                .values(remaining_amount_till_now=remaining_balance, updated_at=datetime.now(timezone.utc))
            )

        await self.db.execute(
            banks.update()
            .where(banks.c.id == expense_row["bank_id"])
            .values(
                current_balance=banks.c.current_balance + amount,
                total_disbursed_till_now=banks.c.total_disbursed_till_now - amount,
            )
        )

        if after_expense_ids:
            await self.db.execute(
                expenses.update()
                .where(expenses.c.id.in_(after_expense_ids))
                .values(remaining_amount_till_now=expenses.c.remaining_amount_till_now + amount)
            )

        await self.db.commit()
        return True

    async def delete_expense(self, user_id: str, expense_id: str) -> bool:
        """Delete an entire expense."""
        if not is_valid_id(expense_id):
            return False

        uid = uuid.UUID(user_id)
        eid = uuid.UUID(expense_id)

        expense_row = (
            await self.db.execute(select(expenses).where(expenses.c.id == eid, expenses.c.user_id == uid))
        ).mappings().first()
        if not expense_row:
            return False

        after_expense_ids = [
            r.id
            for r in (
                await self.db.execute(
                    select(expenses.c.id).where(
                        expenses.c.bank_id == expense_row["bank_id"],
                        expenses.c.user_id == uid,
                        expenses.c.created_at > expense_row["created_at"],
                    )
                )
            ).all()
        ]

        result = await self.db.execute(expenses.delete().where(expenses.c.id == eid))

        if result.rowcount > 0:
            expense_total = float(expense_row["expense_total"])
            await self.db.execute(
                banks.update()
                .where(banks.c.id == expense_row["bank_id"])
                .values(
                    current_balance=banks.c.current_balance + expense_total,
                    total_disbursed_till_now=banks.c.total_disbursed_till_now - expense_total,
                )
            )
            if after_expense_ids:
                await self.db.execute(
                    expenses.update()
                    .where(expenses.c.id.in_(after_expense_ids))
                    .values(remaining_amount_till_now=expenses.c.remaining_amount_till_now + expense_total)
                )
            await self.db.commit()
            return True

        await self.db.commit()
        return False

    async def get_aggregated_data(self, user_id: str, bank_id: Optional[str] = None) -> dict:
        """
        Get aggregated expense data by tags (for graphs).

        FIXES PLAN.md bug #1: the Mongo version matched `user_id` (a string)
        against a field stored as ObjectId, and filtered on a non-existent
        `bank_id` field (the real field was `bank`) - both made the pipeline
        match nothing, so this endpoint always returned {}. Here `user_id`
        and `bank_id` are both real, correctly-typed UUID columns.
        """
        uid = uuid.UUID(user_id)
        e, ee, links, tags = expenses, expense_entries, expense_entry_tag_links, expense_entry_tags

        stmt = (
            select(
                links.c.tag_id,
                func.sum(case((ee.c.amount > 0, ee.c.amount), else_=0)).label("tags_wise_summation"),
            )
            .select_from(
                e.join(ee, ee.c.expense_id == e.c.id).join(links, links.c.expense_entry_id == ee.c.id)
            )
            .where(e.c.user_id == uid)
        )

        if bank_id and is_valid_id(bank_id):
            stmt = stmt.where(e.c.bank_id == uuid.UUID(bank_id))

        stmt = stmt.group_by(links.c.tag_id)

        rows = (await self.db.execute(stmt)).all()
        if not rows:
            return {}

        tag_ids = [r.tag_id for r in rows]
        tag_rows = (
            await self.db.execute(select(tags.c.id, tags.c.name).where(tags.c.id.in_(tag_ids), tags.c.user_id == uid))
        ).all()
        tag_names = {str(t.id): t.name for t in tag_rows}

        result = {}
        for r in rows:
            tag_id_str = str(r.tag_id)
            result[tag_id_str] = {
                "tags_wise_summation": float(r.tags_wise_summation),
                "tag_name": tag_names.get(tag_id_str, "Unknown"),
            }
        return result
