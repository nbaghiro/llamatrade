"""Ingest role: fills the Timescale store from Alpaca.

Two pipelines feed the store: bulk REST backfill (``backfill.py``) for history,
and real-time stream write-through (``stream.py``) for the live tail, with a
calendar-driven gap-repair loop (``gaps.py``) and a corporate-action refresh
(``corporate_actions.py``). The supervisor entrypoint is ``main.py``.

This package shares the store and Alpaca client with the serving role but is
deployed as its own (singleton) workload — see the plan's two-role topology.
"""
