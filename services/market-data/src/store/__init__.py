"""Timescale-backed market-data store.

This package owns the dedicated time-series database that market-data ingests
into and serves from. It is intentionally independent of the shared
``llamatrade_db`` engine (different database, different workload): see
``config.py`` for the dedicated engine and ``repository.py`` for the read/write
interface used by both the ingest and serving roles.
"""
