"""Operator tool: create and list sign-up invite codes.

Run from the auth service (``DATABASE_URL`` must point at the database)::

    python -m src.tools.invites create [--email EMAIL] [--days N] [--quiet]
    python -m src.tools.invites list                                  # CSV to stdout

``make invite-create [EMAIL=...]`` and ``make invite-list`` wrap these. A code
created with ``--email`` is bound to that address and its invite email is sent
through the notification service.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from collections.abc import Sequence
from datetime import timedelta
from typing import TextIO

from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db import close_db, get_session_maker
from llamatrade_db.models.auth import InviteCode
from llamatrade_events.catalog.notifications import NotificationEvents

from src.services.invites import (
    DEFAULT_TTL,
    create_invite,
    format_code,
    invite_link,
    list_invites,
    send_invite_email,
)

CSV_COLUMNS = ("code", "email", "created_at", "expires_at", "used_at", "used_by")


def write_csv(invites: Sequence[InviteCode], out: TextIO) -> None:
    """Codes as CSV with a header row; timestamps in ISO 8601."""
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for invite in invites:
        writer.writerow(
            (
                format_code(invite.code),
                invite.email or "",
                invite.created_at.isoformat(),
                invite.expires_at.isoformat(),
                invite.used_at.isoformat() if invite.used_at else "",
                str(invite.used_by) if invite.used_by else "",
            )
        )


async def issue_invite(
    db: AsyncSession, *, email: str | None, ttl: timedelta, out: TextIO
) -> InviteCode:
    """Create and commit a code; when it has an email, send the invite email too.

    The code is committed before the email is sent, so a failed send leaves a
    valid code and prints the link for sending by hand.
    """
    invite = await create_invite(db, email=email, ttl=ttl)
    await db.commit()
    out.write(f"Code: {format_code(invite.code)} (expires {invite.expires_at:%Y-%m-%d})\n")
    out.write(f"Link: {invite_link(invite.code, invite.email)}\n")
    if invite.email is None:
        return invite
    events = NotificationEvents()
    try:
        await send_invite_email(invite, events)
    except Exception as exc:
        out.write(f"Invite email to {invite.email} was not sent ({exc}); send the link by hand.\n")
        raise
    finally:
        await events.close()
    out.write(f"Invite email queued for {invite.email}\n")
    return invite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage sign-up invite codes.")
    commands = parser.add_subparsers(dest="command", required=True)
    create_cmd = commands.add_parser("create", help="Create a code (and email it, with --email)")
    create_cmd.add_argument("--email", default=None)
    create_cmd.add_argument("--days", type=int, default=DEFAULT_TTL.days)
    create_cmd.add_argument(
        "--quiet", action="store_true", help="Print only the code; never sends email"
    )
    commands.add_parser("list", help="Print codes as CSV")
    return parser


async def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "create" and args.days < 1:
        sys.stderr.write("--days must be at least 1\n")
        return 2
    maker = get_session_maker()
    try:
        async with maker() as db:
            if args.command == "list":
                write_csv(await list_invites(db), sys.stdout)
                return 0
            ttl = timedelta(days=args.days)
            if args.quiet:
                invite = await create_invite(db, email=args.email, ttl=ttl)
                await db.commit()
                sys.stdout.write(f"{invite.code}\n")
                return 0
            try:
                await issue_invite(db, email=args.email, ttl=ttl, out=sys.stdout)
            except Exception:
                return 1
            return 0
    finally:
        await close_db()


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
