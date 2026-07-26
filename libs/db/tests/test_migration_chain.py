"""Structural guardrails on the Alembic revision chain.

These catch the failure modes that only surface on a from-scratch
``alembic upgrade head`` (a fresh CI database), long after the offending
revision was merged against an already-migrated dev database.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ``alembic_version.version_num`` is VARCHAR(32); a longer id inserts fine on the
# revision that defines it and then fails when the *next* revision stamps it.
_VERSION_NUM_MAX = 32

_VERSIONS_DIR = Path(__file__).resolve().parents[1] / "llamatrade_db" / "alembic" / "versions"
_REVISION_RE = re.compile(r'^revision:\s*str\s*=\s*"([^"]+)"', re.M)
_DOWN_REVISION_RE = re.compile(
    r"^down_revision:\s*str\s*\|\s*None\s*=\s*(?:\"([^\"]+)\"|None)", re.M
)


def _migrations() -> list[tuple[str, str | None, str]]:
    """(revision, down_revision, filename) for every migration module."""
    out: list[tuple[str, str | None, str]] = []
    for path in sorted(_VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text()
        rev = _REVISION_RE.search(text)
        if rev is None:
            continue
        down = _DOWN_REVISION_RE.search(text)
        out.append((rev.group(1), down.group(1) if down else None, path.name))
    return out


def test_migrations_are_discovered() -> None:
    """Guard the guards — a broken parser must not silently pass every test here."""
    assert len(_migrations()) > 20


@pytest.mark.parametrize("revision,_down,filename", _migrations())
def test_revision_id_fits_alembic_version_column(
    revision: str, _down: str | None, filename: str
) -> None:
    """Every revision id must fit in alembic_version.version_num."""
    assert len(revision) <= _VERSION_NUM_MAX, (
        f"{filename}: revision id {revision!r} is {len(revision)} chars, "
        f"max {_VERSION_NUM_MAX} — stamping it raises StringDataRightTruncationError"
    )


def test_revision_ids_are_unique() -> None:
    revisions = [rev for rev, _, _ in _migrations()]
    assert len(revisions) == len(set(revisions))


def test_chain_is_linear_and_fully_connected() -> None:
    """Exactly one root, no forks, and every down_revision resolves to a real revision."""
    migrations = _migrations()
    revisions = {rev for rev, _, _ in migrations}

    roots = [(rev, fn) for rev, down, fn in migrations if down is None]
    assert len(roots) == 1, f"expected exactly one root revision, got {roots}"

    for rev, down, filename in migrations:
        if down is not None:
            assert down in revisions, f"{filename}: down_revision {down!r} does not exist"

    parents = [down for _, down, _ in migrations if down is not None]
    assert len(parents) == len(set(parents)), "two revisions share a parent — the chain forks"
