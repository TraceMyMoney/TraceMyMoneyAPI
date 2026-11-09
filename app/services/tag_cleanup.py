"""One-time cleanup: apply the tag naming rule (first letter upper-case, spaces
tidied) to tags that already exist. Used by `scripts/capitalize_tags.py`.

Only `expense_entry_tags.name` is ever written. Entries, links and amounts are
untouched. A tag is SKIPPED (and reported) when its new name would clash with
another tag of the same user, for example `food` next to an existing `Food`;
merging those is left to the user. Safe to run twice: a second run finds
nothing to change.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tables import expense_entry_tags
from app.schemas.entry_tag import normalize_tag_name


@dataclass
class CleanupReport:
    changed: list[tuple[uuid.UUID, str, str]] = field(default_factory=list)  # (user_id, old, new)
    skipped: list[tuple[uuid.UUID, str, str]] = field(default_factory=list)  # (user_id, old, would_be)
    unchanged: int = 0


def plan_cleanup(rows) -> CleanupReport:
    """Decide what to change from (id, user_id, name) rows. Pure, no DB access."""
    report = CleanupReport()
    by_user: dict[uuid.UUID, list] = defaultdict(list)
    for row in rows:
        by_user[row.user_id].append(row)

    for user_id, tags in by_user.items():
        for tag in tags:
            new_name = normalize_tag_name(tag.name)
            if new_name == tag.name:
                report.unchanged += 1
                continue
            clash = any(other.id != tag.id and other.name.lower() == new_name.lower() for other in tags)
            if clash or not new_name:
                report.skipped.append((user_id, tag.name, new_name))
            else:
                report.changed.append((user_id, tag.name, new_name))
    return report


async def capitalize_existing_tags(db: AsyncSession, apply: bool) -> CleanupReport:
    """Report (apply=False) or perform (apply=True) the cleanup. When applying,
    each user's renames are committed in their own transaction."""
    result = await db.execute(select(expense_entry_tags.c.id, expense_entry_tags.c.user_id, expense_entry_tags.c.name))
    rows = result.all()
    report = plan_cleanup(rows)
    if not apply:
        return report

    name_to_id = {(r.user_id, r.name): r.id for r in rows}
    by_user: dict[uuid.UUID, list[tuple[str, str]]] = defaultdict(list)
    for user_id, old, new in report.changed:
        by_user[user_id].append((old, new))

    for user_id, renames in by_user.items():
        for old, new in renames:
            await db.execute(
                update(expense_entry_tags)
                .where(expense_entry_tags.c.id == name_to_id[(user_id, old)], expense_entry_tags.c.user_id == user_id)
                .values(name=new)
            )
        await db.commit()  # one transaction per user
    return report
