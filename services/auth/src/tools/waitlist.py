"""Operator tool: list the marketing waitlist and mark people as invited.

Run from the auth service (``DATABASE_URL`` must point at the database)::

    python -m src.tools.waitlist list [--status waiting|invited]   # CSV to stdout
    python -m src.tools.waitlist invite EMAIL

``make waitlist-list`` and ``make waitlist-invite EMAIL=...`` wrap these.
Inviting marks the entry invited, creates an invite code bound to the email and
sends the invite email through the notification service.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from collections.abc import Sequence
from datetime import timedelta
from typing import TextIO

from llamatrade_db import close_db, get_session_maker
from llamatrade_db.models.auth import (
    WAITLIST_STATUS_INVITED,
    WAITLIST_STATUS_WAITING,
    WaitlistEntry,
)

from src.services.invites import DEFAULT_TTL
from src.services.waitlist import list_entries, mark_invited, normalize_email
from src.tools.invites import issue_invite

CSV_COLUMNS = ("email", "source", "status", "created_at", "invited_at")


def write_csv(entries: Sequence[WaitlistEntry], out: TextIO) -> None:
    """Entries as CSV with a header row; timestamps in ISO 8601."""
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for entry in entries:
        writer.writerow(
            (
                entry.email,
                entry.source,
                entry.status,
                entry.created_at.isoformat(),
                entry.invited_at.isoformat() if entry.invited_at else "",
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the marketing waitlist.")
    commands = parser.add_subparsers(dest="command", required=True)
    list_cmd = commands.add_parser("list", help="Print entries as CSV")
    list_cmd.add_argument(
        "--status", choices=(WAITLIST_STATUS_WAITING, WAITLIST_STATUS_INVITED), default=None
    )
    invite_cmd = commands.add_parser("invite", help="Mark invited and email an invite code")
    invite_cmd.add_argument("email")
    invite_cmd.add_argument("--days", type=int, default=DEFAULT_TTL.days)
    return parser


async def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "invite" and args.days < 1:
        sys.stderr.write("--days must be at least 1\n")
        return 2
    maker = get_session_maker()
    try:
        async with maker() as db:
            if args.command == "list":
                write_csv(await list_entries(db, status=args.status), sys.stdout)
                return 0
            entry = await mark_invited(db, args.email)
            if entry is None:
                sys.stderr.write(f"Not on the waitlist: {normalize_email(args.email)}\n")
                return 1
            await db.commit()
            sys.stdout.write(f"Marked {entry.email} as invited at {entry.invited_at}\n")
            try:
                await issue_invite(
                    db, email=entry.email, ttl=timedelta(days=args.days), out=sys.stdout
                )
            except Exception:
                return 1
            return 0
    finally:
        await close_db()


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
