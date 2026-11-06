"""Keep the saved chats only as long as they are needed: list, then delete, the chats older than N days.

    python -m scripts.prune_chats                 # the chats older than 30 days, listed: nothing is deleted
    python -m scripts.prune_chats --days 7        # another limit
    python -m scripts.prune_chats --delete        # delete them

A chat's age is the time it started, read from its name (`2026-09-30_153012.jsonl`), else the time the file
was last written. The chats hold what the coaches typed: keeping them for a limited time is part of the answer
to "where does the data go" (see "Data and privacy" in the README). The traces in Phoenix are kept in the
Docker volume `phoenix_data` and go with it (`docker compose down -v` deletes the index too). No key, no network.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import src.core.config as config

DEFAULT_DAYS = 30


def started(path: Path) -> datetime:
    """When the chat of `path` started: from its name, else from the file."""
    try:
        return datetime.strptime(path.stem[:17], "%Y-%m-%d_%H%M%S")
    except ValueError:
        return datetime.fromtimestamp(path.stat().st_mtime)


def old_chats(folder: Path, days: int, now: datetime | None = None) -> list[Path]:
    """The chat files of `folder` started more than `days` days before `now`, oldest first."""
    limit = (now or datetime.now()) - timedelta(days=days)
    return sorted((p for p in folder.glob("*.jsonl") if started(p) < limit), key=started)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help=f"keep the last N days (default {DEFAULT_DAYS})")
    parser.add_argument("--delete", action="store_true", help="delete the old chats (without it they are only listed)")
    parser.add_argument("--folder", type=Path, default=config.CHATS_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.days < 0:
        parser.error("--days must be 0 or more")
    if not args.folder.is_dir():
        print(f"No saved chats ({args.folder.name}/ does not exist).")
        return 0
    old = old_chats(args.folder, args.days)
    kept = len(list(args.folder.glob("*.jsonl"))) - len(old)
    for path in old:
        print(f"{'deleted' if args.delete else 'older than the limit'}: {path.name} (started {started(path):%Y-%m-%d})")
        if args.delete:
            path.unlink()
    print(f"\n{len(old)} chats older than {args.days} days, {kept} kept.")
    if old and not args.delete:
        print("Nothing deleted: add --delete to delete them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
