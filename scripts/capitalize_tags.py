"""
One-time cleanup of existing tag names (tags-crud feature): upper-case the first
letter and tidy spaces, so old tags match the new naming rule ("food" -> "Food").

Dry run by default: prints what WOULD change and changes nothing. Add --apply to
write. Only tag names are renamed; entries, links and amounts are never touched.
A tag whose new name would clash with another tag of the same user (for example
`food` next to `Food`) is skipped and listed, so you can sort those out by hand.
Safe to run twice.

Usage:
    uv run python scripts/capitalize_tags.py            # dry run, read the report
    uv run python scripts/capitalize_tags.py --apply    # write the changes

On production:
    docker exec stalkmymoney_api uv run python scripts/capitalize_tags.py
    docker exec stalkmymoney_api uv run python scripts/capitalize_tags.py --apply
"""

import argparse
import asyncio
import os
import sys

# Allow `uv run python scripts/capitalize_tags.py` (only scripts/ is on sys.path then).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.postgres import AsyncSessionLocal, engine  # noqa: E402
from app.services.tag_cleanup import capitalize_existing_tags  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the changes (default is a dry run)")
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        report = await capitalize_existing_tags(db, apply=args.apply)
    await engine.dispose()

    mode = "APPLIED" if args.apply else "DRY RUN (nothing was changed)"
    print(f"Tag capitalization: {mode}")
    print(f"  already fine : {report.unchanged}")
    print(f"  {'renamed' if args.apply else 'would rename'}: {len(report.changed)}")
    for user_id, old, new in report.changed:
        print(f"    user {user_id}: '{old}' -> '{new}'")
    print(f"  skipped (would clash with another tag): {len(report.skipped)}")
    for user_id, old, new in report.skipped:
        print(f"    user {user_id}: '{old}' would become '{new}' but that name is taken; fix by hand")
    if not args.apply and report.changed:
        print("Run again with --apply to write these changes.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
