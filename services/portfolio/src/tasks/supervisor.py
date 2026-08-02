"""Supervision + leadership types for the long-running ledger loops.

``supervise`` (shared, from llamatrade_common) restarts a crashed loop with
capped exponential backoff. ``LeadershipProbe`` is the ledger-specific
"do I still hold the writer lock?" callable bound by ``tasks/writer_election.py``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from llamatrade_common import supervise

LeadershipProbe = Callable[[], Awaitable[bool]]

__all__ = ["LeadershipProbe", "supervise"]
