# Market Data Storage with TimescaleDB

> **Status:** Future implementation (post-MVP)
> **Current approach:** Redis caching for MVP
> **When to revisit:** Heavy backtesting load, need for historical analysis, >100 backtests/day

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Why TimescaleDB](#why-timescaledb)
3. [TimescaleDB Core Concepts](#timescaledb-core-concepts)
4. [Architecture Overview](#architecture-overview)
5. [Data Models](#data-models)
6. [Ingestion Pipeline](#ingestion-pipeline)
7. [Query Patterns](#query-patterns)
8. [Compression & Retention](#compression--retention)
9. [Cost Analysis](#cost-analysis)
10. [Migration Path](#migration-path)
11. [Operational Runbook](#operational-runbook)

---

## Executive Summary

This document outlines a production-grade market data storage solution using TimescaleDB for LlamaTrade. The solution handles:

- **8,000+ US equity symbols**
- **1-minute OHLCV bars** (~784 million rows/year)
- **Real-time quote streaming**
- **Historical backfill** (years of data)
- **Sub-second query performance** for backtesting

**Key benefits over vanilla PostgreSQL:**

- 90-95% storage compression
- Automatic time-based partitioning
- Built-in downsampling (continuous aggregates)
- Optimized time-range queries

---

## Why TimescaleDB

### The Problem with Regular PostgreSQL

```
                    POSTGRESQL WITH 784 MILLION ROWS

    Query: SELECT * FROM bars WHERE symbol='AAPL' AND timestamp > '2024-01-01'

    ┌─────────────────────────────────────────────────────────────────┐
    │                        SINGLE MASSIVE TABLE                     │
    │  ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐  │
    │  │AAPL │GOOGL│MSFT │AAPL │TSLA │AAPL │NVDA │AAPL │META │AAPL │  │
    │  │2020 │2021 │2020 │2023 │2022 │2021 │2024 │2024 │2023 │2020 │  │
    │  └─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘  │
    │                                                                 │
    │  Problem: Data scattered randomly across disk                   │
    │  Result:  FULL TABLE SCAN → Minutes to query                    │
    └─────────────────────────────────────────────────────────────────┘
```

### How TimescaleDB Solves This

```
                    TIMESCALEDB HYPERTABLE (SAME DATA)

    Query: SELECT * FROM bars WHERE symbol='AAPL' AND timestamp > '2024-01-01'

    ┌─────────────────────────────────────────────────────────────────┐
    │                         HYPERTABLE                              │
    │         (Looks like one table, actually many chunks)            │
    │                                                                 │
    │ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ │
    │ │ Chunk: 2020 │ │ Chunk: 2021 │ │ Chunk: 2022 │ │ Chunk: 2023 │ │
    │ │ Jan-Mar     │ │ Jan-Mar     │ │ Jan-Mar     │ │ Jan-Mar     │ │
    │ │ (SKIP)      │ │ (SKIP)      │ │ (SKIP)      │ │ (SKIP)      │ │
    │ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ │
    │ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ │
    │ │ Chunk: 2020 │ │ Chunk: 2021 │ │ Chunk: 2022 │ │ Chunk: 2023 │ │
    │ │ Apr-Jun     │ │ Apr-Jun     │ │ Apr-Jun     │ │ Apr-Jun     │ │
    │ │ (SKIP)      │ │ (SKIP)      │ │ (SKIP)      │ │ (SKIP)      │ │
    │ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ │
    │                        ...                                      │
    │  ┌─────────────┐                                                │
    │  │ Chunk: 2024 │ ◄── ONLY THIS CHUNK SCANNED                    │
    │  │ Jan-Mar     │     (Chunk exclusion via timestamp filter)     │
    │  │ AAPL,GOOGL..│                                                │
    │  └─────────────┘                                                │
    │                                                                 │
    │  Result: Scan 0.1% of data → Milliseconds to query              │
    └─────────────────────────────────────────────────────────────────┘
```

---

## TimescaleDB Core Concepts

### 1. Hypertables & Chunks

A **hypertable** is TimescaleDB's abstraction over a regular PostgreSQL table. You interact with it like a normal table, but internally it's partitioned into **chunks**.

```
                           HYPERTABLE: bars
                                  │
           ┌──────────────────────┼──────────────────────┐
           │                      │                      │
           ▼                      ▼                      ▼
    ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
    │   Chunk 1   │        │   Chunk 2   │        │   Chunk 3   │
    │ 2024-01-01  │        │ 2024-01-08  │        │ 2024-01-15  │
    │     to      │        │     to      │        │     to      │
    │ 2024-01-07  │        │ 2024-01-14  │        │ 2024-01-21  │
    │             │        │             │        │             │
    │ ~22M rows   │        │ ~22M rows   │        │ ~22M rows   │
    │ (1 week)    │        │ (1 week)    │        │ (1 week)    │
    └─────────────┘        └─────────────┘        └─────────────┘

    INSERT INTO bars (...)  →  Automatically routed to correct chunk
    SELECT FROM bars WHERE timestamp > '2024-01-10'  →  Only scans chunks 2, 3
```

**Why this matters:**

- Queries with time filters skip irrelevant chunks entirely
- Old chunks can be compressed independently
- Dropping old data = dropping chunks (instant, no vacuum)
- Each chunk is sized for optimal memory/cache usage

### 2. Compression

TimescaleDB compression is **columnar** and designed for time-series patterns.

```
                         BEFORE COMPRESSION

    ┌────────┬─────────────────────┬────────┬────────┬────────┐
    │ symbol │ timestamp           │ open   │ high   │ close  │
    ├────────┼─────────────────────┼────────┼────────┼────────┤
    │ AAPL   │ 2024-01-15 09:30:00 │ 185.23 │ 185.45 │ 185.40 │
    │ AAPL   │ 2024-01-15 09:31:00 │ 185.40 │ 185.52 │ 185.48 │
    │ AAPL   │ 2024-01-15 09:32:00 │ 185.48 │ 185.50 │ 185.35 │
    │ AAPL   │ 2024-01-15 09:33:00 │ 185.35 │ 185.42 │ 185.38 │
    │ AAPL   │ 2024-01-15 09:34:00 │ 185.38 │ 185.55 │ 185.50 │
    └────────┴─────────────────────┴────────┴────────┴────────┘

    Storage: ~150 bytes per row × 5 rows = 750 bytes


                         AFTER COMPRESSION

    ┌─────────────────────────────────────────────────────────┐
    │ Compressed Segment (symbol = 'AAPL')                    │
    ├─────────────────────────────────────────────────────────┤
    │ symbol:    [AAPL] (stored once via dictionary encoding) │
    │ timestamp: [delta-encoded array: 09:30, +1m, +1m, ...]  │
    │ open:      [gorilla-compressed: 185.23, Δ0.17, Δ0.08..] │
    │ high:      [gorilla-compressed: 185.45, Δ0.07, ...]     │
    │ close:     [gorilla-compressed: 185.40, Δ0.08, ...]     │
    └─────────────────────────────────────────────────────────┘

    Storage: ~50-80 bytes total (90%+ reduction)


    WHY IT WORKS SO WELL FOR FINANCIAL DATA:

    ┌────────────────────────────────────────────────────────────┐
    │ Financial prices have HIGH correlation between rows:       │
    │                                                            │
    │   AAPL price at 09:30 = 185.23                             │
    │   AAPL price at 09:31 = 185.40  (Δ = +0.17)                │
    │   AAPL price at 09:32 = 185.48  (Δ = +0.08)                │
    │                                                            │
    │ Delta encoding stores: [185.23, +0.17, +0.08, ...]         │
    │ Small deltas = fewer bits needed = massive compression     │
    └────────────────────────────────────────────────────────────┘
```

**Compression strategy for LlamaTrade:**

```sql
-- Segment by symbol (all AAPL rows compressed together)
-- Order by timestamp descending (recent data accessed more)
ALTER TABLE bars SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Automatically compress chunks older than 7 days
SELECT add_compression_policy('bars', INTERVAL '7 days');
```

### 3. Continuous Aggregates

Pre-computed rollups that **automatically stay in sync** with raw data.

```
                    CONTINUOUS AGGREGATES

    ┌─────────────────────────────────────────────────────────────┐
    │                      RAW DATA (1-min bars)                  │
    │                                                             │
    │  09:30  09:31  09:32  09:33  09:34  ...  16:29  16:30       │
    │    │      │      │      │      │           │      │         │
    │    ▼      ▼      ▼      ▼      ▼           ▼      ▼         │
    │  ┌────┬────┬────┬────┬────┬─────────┬────┬────┐             │
    │  │ O  │ O  │ O  │ O  │ O  │   ...   │ O  │ O  │  390 bars   │
    │  │ H  │ H  │ H  │ H  │ H  │         │ H  │ H  │  per symbol │
    │  │ L  │ L  │ L  │ L  │ L  │         │ L  │ L  │  per day    │
    │  │ C  │ C  │ C  │ C  │ C  │         │ C  │ C  │             │
    │  │ V  │ V  │ V  │ V  │ V  │         │ V  │ V  │             │
    │  └────┴────┴────┴────┴────┴─────────┴────┴────┘             │
    └─────────────────────────────────────────────────────────────┘
                              │
                              │ Automatic materialization
                              ▼
    ┌───────────────────────────────────────────────────────────────┐
    │                 CONTINUOUS AGGREGATE (1-hour bars)            │
    │                                                               │
    │     09:00-10:00    10:00-11:00    ...    15:00-16:00          │
    │         │              │                     │                │
    │         ▼              ▼                     ▼                │
    │     ┌────────┐    ┌────────┐           ┌────────┐             │
    │     │ O=first│    │ O=first│           │ O=first│   7 bars    │
    │     │ H=max  │    │ H=max  │           │ H=max  │   per sym   │
    │     │ L=min  │    │ L=min  │           │ L=min  │   per day   │
    │     │ C=last │    │ C=last │           │ C=last │             │
    │     │ V=sum  │    │ V=sum  │           │ V=sum  │             │
    │     └────────┘    └────────┘           └────────┘             │
    └───────────────────────────────────────────────────────────────┘
                              │
                              │ Automatic materialization
                              ▼
    ┌───────────────────────────────────────────────────────────────┐
    │                 CONTINUOUS AGGREGATE (1-day bars)             │
    │                                                               │
    │                      2024-01-15                               │
    │                          │                                    │
    │                          ▼                                    │
    │                     ┌────────┐                                │
    │                     │ O=first│    1 bar per symbol per day    │
    │                     │ H=max  │                                │
    │                     │ L=min  │    Query this for long-term    │
    │                     │ C=last │    backtests (instant!)        │
    │                     │ V=sum  │                                │
    │                     └────────┘                                │
    └───────────────────────────────────────────────────────────────┘


    QUERY ROUTING:

    User query: "Give me AAPL daily bars for 2023"

    Without continuous aggregates:
      → Scan 98,000 1-min bars, aggregate on the fly
      → Slow, CPU intensive

    With continuous aggregates:
      → Query pre-computed daily bars table
      → 252 rows, instant response
```

**SQL to create continuous aggregates:**

```sql
-- Hourly bars from 1-minute data
CREATE MATERIALIZED VIEW bars_1h
WITH (timescaledb.continuous) AS
SELECT
    symbol,
    time_bucket('1 hour', timestamp) AS timestamp,
    first(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, timestamp) AS close,
    sum(volume) AS volume,
    sum(volume * (high + low + close) / 3) / sum(volume) AS vwap,
    sum(trade_count) AS trade_count
FROM bars
GROUP BY symbol, time_bucket('1 hour', timestamp);

-- Daily bars from hourly (cascading aggregates)
CREATE MATERIALIZED VIEW bars_1d
WITH (timescaledb.continuous) AS
SELECT
    symbol,
    time_bucket('1 day', timestamp) AS timestamp,
    first(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, timestamp) AS close,
    sum(volume) AS volume,
    sum(volume * (high + low + close) / 3) / sum(volume) AS vwap,
    sum(trade_count) AS trade_count
FROM bars_1h
GROUP BY symbol, time_bucket('1 day', timestamp);

-- Auto-refresh policies
SELECT add_continuous_aggregate_policy('bars_1h',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

SELECT add_continuous_aggregate_policy('bars_1d',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day');
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MARKET DATA ARCHITECTURE                          │
└─────────────────────────────────────────────────────────────────────────────┘

                           ┌──────────────────┐
                           │  ALPACA MARKETS  │
                           │       API        │
                           └────────┬─────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
           ┌────────────┐  ┌────────────┐  ┌────────────┐
           │  REST API  │  │ WebSocket  │  │ Historical │
           │  (quotes)  │  │ (realtime) │  │  (backfill)│
           └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
                 │               │               │
                 └───────────────┼───────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MARKET DATA SERVICE                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      INGESTION WORKERS                              │    │
│  │                                                                     │    │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │    │
│  │   │  Realtime   │    │   Daily     │    │  Backfill   │             │    │
│  │   │  Streamer   │    │   Sync      │    │   Worker    │             │    │
│  │   │             │    │  (cron)     │    │  (one-time) │             │    │
│  │   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘             │    │
│  │          │                  │                  │                    │    │
│  │          └──────────────────┼──────────────────┘                    │    │
│  │                             │                                       │    │
│  │                             ▼                                       │    │
│  │                    ┌─────────────────┐                              │    │
│  │                    │  Write Buffer   │                              │    │
│  │                    │  (batch inserts)│                              │    │
│  │                    └────────┬────────┘                              │    │
│  └─────────────────────────────┼───────────────────────────────────────┘    │
│                                │                                            │
│  ┌─────────────────────────────┼───────────────────────────────────────┐    │
│  │                             ▼                                       │    │
│  │  ┌───────────────────────────────────────────────────────────────┐  │    │
│  │  │                      TIMESCALEDB                              │  │    │
│  │  │                                                               │  │    │
│  │  │   ┌────────────────────────────────────────────────────┐      │  │    │
│  │  │   │              HYPERTABLE: bars                      │      │  │    │
│  │  │   │                                                    │      │  │    │
│  │  │   │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │      │  │    │
│  │  │   │  │ Chunk 1 │ │ Chunk 2 │ │ Chunk 3 │ │ Chunk N │   │      │  │    │
│  │  │   │  │ (compr) │ │ (compr) │ │ (compr) │ │ (live)  │   │      │  │    │
│  │  │   │  └─────────┘ └─────────┘ └─────────┘ └─────────┘   │      │  │    │
│  │  │   └────────────────────────────────────────────────────┘      │  │    │
│  │  │                             │                                 │  │    │
│  │  │              ┌──────────────┼──────────────┐                  │  │    │
│  │  │              ▼              ▼              ▼                  │  │    │
│  │  │   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │  │    │
│  │  │   │   bars_1h    │ │   bars_1d    │ │   bars_1w    │          │  │    │
│  │  │   │  (cont.agg)  │ │  (cont.agg)  │ │  (cont.agg)  │          │  │    │
│  │  │   └──────────────┘ └──────────────┘ └──────────────┘          │  │    │
│  │  │                                                               │  │    │
│  │  └───────────────────────────────────────────────────────────────┘  │    │
│  │                                                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                │                                            │
└────────────────────────────────┼────────────────────────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────┴──────────────────┐
              │                                     │
              ▼                                     ▼
    ┌──────────────────┐                 ┌──────────────────┐
    │  BACKTEST SVC    │                 │  TRADING SVC     │
    │                  │                 │                  │
    │  Reads bars_1d   │                 │  Reads latest    │
    │  for long-term   │                 │  bars for risk   │
    │  simulations     │                 │  checks          │
    └──────────────────┘                 └──────────────────┘


                         REDIS CACHE LAYER
    ┌─────────────────────────────────────────────────────────────┐
    │                                                             │
    │   For HOT DATA (latest bars, active symbols):               │
    │                                                             │
    │   ┌─────────────────┐    ┌─────────────────┐                │
    │   │ bars:AAPL:1min  │    │ bars:AAPL:1d    │                │
    │   │ (last 60 mins)  │    │ (last 30 days)  │                │
    │   └─────────────────┘    └─────────────────┘                │
    │                                                             │
    │   TTL: 1 hour (1min data), 24 hours (daily data)            │
    │   Populated on-demand, refreshed from TimescaleDB           │
    │                                                             │
    └─────────────────────────────────────────────────────────────┘
```

---

## Data Models

### SQLAlchemy Models (TimescaleDB-aware)

```python
# libs/db/llamatrade_db/models/market_data.py

from sqlalchemy import (
    Column, String, DateTime, Numeric, BigInteger,
    Index, text, DDL, event
)
from sqlalchemy.dialects.postgresql import JSONB
from llamatrade_db.base import Base


class Bar(Base):
    """
    1-minute OHLCV bars - primary market data table.

    Converted to TimescaleDB hypertable with:
    - Automatic time-based partitioning (1 week chunks)
    - Compression after 7 days
    - Continuous aggregates for 1h, 1d, 1w timeframes
    """
    __tablename__ = "bars"

    # Composite primary key: (symbol, timestamp)
    symbol = Column(String(10), primary_key=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), primary_key=True, nullable=False)

    # OHLCV data
    open = Column(Numeric(18, 8), nullable=False)
    high = Column(Numeric(18, 8), nullable=False)
    low = Column(Numeric(18, 8), nullable=False)
    close = Column(Numeric(18, 8), nullable=False)
    volume = Column(BigInteger, nullable=False)

    # Additional metrics
    vwap = Column(Numeric(18, 8), nullable=True)
    trade_count = Column(BigInteger, nullable=True)

    __table_args__ = (
        # Index for symbol + time range queries (most common pattern)
        Index('ix_bars_symbol_timestamp', 'symbol', 'timestamp'),
        # Index for time-only queries (market-wide analysis)
        Index('ix_bars_timestamp', 'timestamp'),
    )


class Quote(Base):
    """
    Real-time quote snapshots (bid/ask).

    Higher volume than bars - consider shorter retention (30 days).
    """
    __tablename__ = "quotes"

    symbol = Column(String(10), primary_key=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), primary_key=True, nullable=False)

    bid_price = Column(Numeric(18, 8), nullable=False)
    bid_size = Column(BigInteger, nullable=False)
    ask_price = Column(Numeric(18, 8), nullable=False)
    ask_size = Column(BigInteger, nullable=False)

    bid_exchange = Column(String(10), nullable=True)
    ask_exchange = Column(String(10), nullable=True)
    conditions = Column(JSONB, nullable=True)

    __table_args__ = (
        Index('ix_quotes_symbol_timestamp', 'symbol', 'timestamp'),
    )


class Trade(Base):
    """
    Individual trade executions (tick data).

    Highest volume - consider storing only for specific symbols
    or shorter retention (7 days).
    """
    __tablename__ = "trades"

    symbol = Column(String(10), primary_key=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), primary_key=True, nullable=False)
    trade_id = Column(String(50), primary_key=True, nullable=False)

    price = Column(Numeric(18, 8), nullable=False)
    size = Column(BigInteger, nullable=False)
    exchange = Column(String(10), nullable=True)
    conditions = Column(JSONB, nullable=True)
    tape = Column(String(1), nullable=True)

    __table_args__ = (
        Index('ix_trades_symbol_timestamp', 'symbol', 'timestamp'),
    )


# TimescaleDB setup DDL (run after table creation)
TIMESCALE_SETUP = """
-- Convert tables to hypertables
SELECT create_hypertable('bars', 'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

SELECT create_hypertable('quotes', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

SELECT create_hypertable('trades', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Enable compression
ALTER TABLE bars SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol',
    timescaledb.compress_orderby = 'timestamp DESC'
);

ALTER TABLE quotes SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol',
    timescaledb.compress_orderby = 'timestamp DESC'
);

ALTER TABLE trades SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Compression policies
SELECT add_compression_policy('bars', INTERVAL '7 days');
SELECT add_compression_policy('quotes', INTERVAL '1 day');
SELECT add_compression_policy('trades', INTERVAL '1 day');

-- Retention policies (optional - adjust based on needs)
-- SELECT add_retention_policy('quotes', INTERVAL '30 days');
-- SELECT add_retention_policy('trades', INTERVAL '7 days');
"""
```

### Continuous Aggregates Setup

```sql
-- migrations/versions/xxx_create_continuous_aggregates.sql

-- 5-minute bars
CREATE MATERIALIZED VIEW bars_5m
WITH (timescaledb.continuous) AS
SELECT
    symbol,
    time_bucket('5 minutes', timestamp) AS timestamp,
    first(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, timestamp) AS close,
    sum(volume) AS volume,
    -- Proper VWAP calculation
    CASE
        WHEN sum(volume) > 0
        THEN sum(volume * vwap) / sum(volume)
        ELSE NULL
    END AS vwap,
    sum(trade_count) AS trade_count
FROM bars
GROUP BY symbol, time_bucket('5 minutes', timestamp)
WITH NO DATA;

-- 1-hour bars
CREATE MATERIALIZED VIEW bars_1h
WITH (timescaledb.continuous) AS
SELECT
    symbol,
    time_bucket('1 hour', timestamp) AS timestamp,
    first(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, timestamp) AS close,
    sum(volume) AS volume,
    CASE
        WHEN sum(volume) > 0
        THEN sum(volume * vwap) / sum(volume)
        ELSE NULL
    END AS vwap,
    sum(trade_count) AS trade_count
FROM bars
GROUP BY symbol, time_bucket('1 hour', timestamp)
WITH NO DATA;

-- 1-day bars
CREATE MATERIALIZED VIEW bars_1d
WITH (timescaledb.continuous) AS
SELECT
    symbol,
    time_bucket('1 day', timestamp) AS timestamp,
    first(open, timestamp) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, timestamp) AS close,
    sum(volume) AS volume,
    CASE
        WHEN sum(volume) > 0
        THEN sum(volume * vwap) / sum(volume)
        ELSE NULL
    END AS vwap,
    sum(trade_count) AS trade_count
FROM bars_1h
GROUP BY symbol, time_bucket('1 day', timestamp)
WITH NO DATA;

-- Refresh policies
SELECT add_continuous_aggregate_policy('bars_5m',
    start_offset => INTERVAL '30 minutes',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes'
);

SELECT add_continuous_aggregate_policy('bars_1h',
    start_offset => INTERVAL '4 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);

SELECT add_continuous_aggregate_policy('bars_1d',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day'
);
```

---

## Ingestion Pipeline

### Pipeline Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INGESTION PIPELINE                                  │
└─────────────────────────────────────────────────────────────────────────────┘

    1. HISTORICAL BACKFILL (one-time or periodic)
    ─────────────────────────────────────────────

    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌──────────┐
    │   Symbol    │     │   Alpaca    │     │   Batch     │     │ Timescale│
    │   List      │────▶│   Client    │────▶│   Writer    │────▶│   DB     │
    │ (8000 sym)  │     │  (parallel) │     │ (1000 rows) │     │          │
    └─────────────┘     └─────────────┘     └─────────────┘     └──────────┘

    Approach:
    - Chunk symbols into batches of 100
    - Fetch 1 year of data per symbol (rate limited)
    - Use COPY for bulk inserts (10x faster than INSERT)
    - Progress tracking in Redis for resumability


    2. DAILY SYNC (cron: 5:00 PM ET after market close)
    ────────────────────────────────────────────────────

    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │   Cron      │     │   Fetch     │     │   Upsert    │
    │   Trigger   │────▶│   Today's   │────▶│   Missing   │
    │  (5 PM ET)  │     │   Bars      │     │   Bars      │
    └─────────────┘     └─────────────┘     └─────────────┘


    3. REAL-TIME STREAMING (market hours only)
    ──────────────────────────────────────────

    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌──────────┐
    │   Alpaca    │     │  WebSocket  │     │   Buffer    │     │ Timescale│
    │  Streaming  │────▶│   Handler   │────▶│  (100 rows  │────▶│   DB     │
    │    API      │     │             │     │  or 1 sec)  │     │          │
    └─────────────┘     └─────────────┘     └─────────────┘     └──────────┘
                                                  │
                                                  │ Parallel
                                                  ▼
                                           ┌──────────┐
                                           │  Redis   │
                                           │ (latest) │
                                           └──────────┘
```

### Backfill Worker Implementation

```python
# services/market-data/src/workers/backfill.py

import asyncio
from datetime import datetime, timedelta
from typing import AsyncIterator

import asyncpg
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from llamatrade_common.config import settings
from llamatrade_common.logging import get_logger

logger = get_logger(__name__)


class BackfillWorker:
    """
    Historical data backfill worker.

    Fetches historical bars from Alpaca and bulk-inserts into TimescaleDB.
    Designed for resumability and rate-limit awareness.
    """

    def __init__(
        self,
        symbols: list[str],
        start_date: datetime,
        end_date: datetime,
        batch_size: int = 100,
        concurrent_fetches: int = 5,
    ):
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.batch_size = batch_size
        self.concurrent_fetches = concurrent_fetches

        self.client = StockHistoricalDataClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY,
        )
        self.pool: asyncpg.Pool | None = None

    async def run(self) -> None:
        """Execute the backfill process."""
        self.pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=5,
            max_size=20,
        )

        try:
            # Process symbols in batches with concurrency limit
            semaphore = asyncio.Semaphore(self.concurrent_fetches)
            tasks = [
                self._fetch_and_store_symbol(symbol, semaphore)
                for symbol in self.symbols
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log results
            success = sum(1 for r in results if not isinstance(r, Exception))
            failed = sum(1 for r in results if isinstance(r, Exception))
            logger.info(f"Backfill complete: {success} succeeded, {failed} failed")

        finally:
            await self.pool.close()

    async def _fetch_and_store_symbol(
        self,
        symbol: str,
        semaphore: asyncio.Semaphore,
    ) -> int:
        """Fetch and store bars for a single symbol."""
        async with semaphore:
            logger.info(f"Fetching {symbol} from {self.start_date} to {self.end_date}")

            try:
                # Fetch from Alpaca (handles pagination internally)
                request = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=TimeFrame.Minute,
                    start=self.start_date,
                    end=self.end_date,
                )
                bars = self.client.get_stock_bars(request)

                # Convert to tuples for COPY
                rows = [
                    (
                        symbol,
                        bar.timestamp,
                        float(bar.open),
                        float(bar.high),
                        float(bar.low),
                        float(bar.close),
                        bar.volume,
                        float(bar.vwap) if bar.vwap else None,
                        bar.trade_count,
                    )
                    for bar in bars[symbol]
                ]

                # Bulk insert using COPY (fastest method)
                async with self.pool.acquire() as conn:
                    await conn.copy_records_to_table(
                        'bars',
                        records=rows,
                        columns=[
                            'symbol', 'timestamp', 'open', 'high', 'low',
                            'close', 'volume', 'vwap', 'trade_count'
                        ],
                    )

                logger.info(f"Stored {len(rows)} bars for {symbol}")
                return len(rows)

            except Exception as e:
                logger.error(f"Failed to backfill {symbol}: {e}")
                raise


class DailySyncWorker:
    """
    Daily sync worker - runs after market close.

    Fetches any missing bars for the current day and upserts them.
    Handles gaps from market holidays, early closes, etc.
    """

    async def run(self) -> None:
        """Sync today's data for all symbols."""
        # Implementation similar to backfill but for single day
        # Uses INSERT ... ON CONFLICT for upsert
        pass


class RealtimeStreamer:
    """
    Real-time streaming worker - runs during market hours.

    Connects to Alpaca WebSocket, buffers bars, and batch-inserts.
    Also updates Redis cache for hot data.
    """

    def __init__(self, symbols: list[str]):
        self.symbols = symbols
        self.buffer: list[tuple] = []
        self.buffer_size = 100
        self.flush_interval = 1.0  # seconds

    async def run(self) -> None:
        """Start streaming and processing."""
        # Connect to Alpaca WebSocket
        # Subscribe to bar updates for symbols
        # Buffer incoming bars
        # Flush to DB when buffer full or interval elapsed
        # Update Redis cache with latest bars
        pass
```

---

## Query Patterns

### Common Queries and Optimization

```sql
-- ============================================
-- QUERY 1: Single symbol, date range (Backtest)
-- ============================================
-- Used by: BacktestService
-- Frequency: High (every backtest run)
-- Expected: <100ms for 1 year of daily data

SELECT * FROM bars_1d
WHERE symbol = 'AAPL'
  AND timestamp >= '2023-01-01'
  AND timestamp < '2024-01-01'
ORDER BY timestamp;

-- Optimization: Uses continuous aggregate (bars_1d)
-- Chunk exclusion on timestamp
-- Index on (symbol, timestamp)


-- ============================================
-- QUERY 2: Multiple symbols, date range (Portfolio backtest)
-- ============================================
-- Used by: BacktestService (multi-asset strategies)
-- Frequency: Medium

SELECT * FROM bars_1d
WHERE symbol = ANY(ARRAY['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'META'])
  AND timestamp >= '2023-01-01'
  AND timestamp < '2024-01-01'
ORDER BY timestamp, symbol;

-- Optimization: Uses continuous aggregate
-- Consider materialized view for common portfolios


-- ============================================
-- QUERY 3: Latest bar for symbol (Trading)
-- ============================================
-- Used by: TradingService, risk checks
-- Frequency: Very high
-- Expected: <10ms

SELECT * FROM bars
WHERE symbol = 'AAPL'
ORDER BY timestamp DESC
LIMIT 1;

-- Optimization: Index on (symbol, timestamp DESC)
-- Cache in Redis for sub-ms response


-- ============================================
-- QUERY 4: Market-wide snapshot (Dashboard)
-- ============================================
-- Used by: Dashboard, market overview
-- Frequency: Low

SELECT symbol,
       last(close, timestamp) as last_price,
       first(open, timestamp) as day_open,
       max(high) as day_high,
       min(low) as day_low,
       sum(volume) as day_volume
FROM bars
WHERE timestamp >= CURRENT_DATE
GROUP BY symbol;

-- Optimization: Continuous aggregate for current day
-- Or pre-compute in Redis


-- ============================================
-- QUERY 5: VWAP calculation (Indicator)
-- ============================================
-- Used by: Strategy indicators
-- Frequency: Medium

SELECT symbol,
       timestamp,
       sum(volume * (high + low + close) / 3) OVER w / sum(volume) OVER w as vwap
FROM bars
WHERE symbol = 'AAPL'
  AND timestamp >= CURRENT_DATE
WINDOW w AS (ORDER BY timestamp ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW);
```

### Index Strategy

```sql
-- Primary access patterns and their indexes

-- Pattern 1: Symbol + time range (most common)
CREATE INDEX ix_bars_symbol_timestamp ON bars (symbol, timestamp DESC);

-- Pattern 2: Time range only (market analysis)
CREATE INDEX ix_bars_timestamp ON bars (timestamp DESC);

-- Pattern 3: Latest bar per symbol (trading)
-- Covered by ix_bars_symbol_timestamp with DESC

-- Continuous aggregates have automatic indexes
-- No additional indexes needed for bars_1h, bars_1d, etc.
```

---

## Compression & Retention

### Storage Projections

```
                    STORAGE ANALYSIS (8,000 symbols, 1-min bars)

    ┌─────────────────────────────────────────────────────────────────────┐
    │                        UNCOMPRESSED                                 │
    │                                                                     │
    │   Per bar: ~150 bytes (symbol, timestamp, OHLCV, vwap, count)       │
    │   Per symbol/year: 98,000 bars × 150 bytes = 14.7 MB                │
    │   Total/year: 8,000 symbols × 14.7 MB = 117.6 GB                    │
    │                                                                     │
    │   5 years = ~588 GB                                                 │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ TimescaleDB Compression
                                    │ (90-95% reduction)
                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │                         COMPRESSED                                  │
    │                                                                     │
    │   Per bar: ~10-15 bytes (after compression)                         │
    │   Per symbol/year: 98,000 bars × 12 bytes = 1.2 MB                  │
    │   Total/year: 8,000 symbols × 1.2 MB = 9.6 GB                       │
    │                                                                     │
    │   5 years = ~48 GB                                                  │
    │                                                                     │
    │   + Continuous aggregates overhead: ~2 GB                           │
    │   + Indexes: ~5 GB                                                  │
    │   ─────────────────────────────────                                 │
    │   TOTAL 5-YEAR STORAGE: ~55 GB                                      │
    └─────────────────────────────────────────────────────────────────────┘


                    COMPRESSION RATIO BY DATA TYPE

    ┌──────────────┬─────────────────┬──────────────────┬────────────────┐
    │   Column     │  Uncompressed   │   Compressed     │     Ratio      │
    ├──────────────┼─────────────────┼──────────────────┼────────────────┤
    │ symbol       │ 10 bytes/row    │ <1 byte/row      │ ~95% (dict)    │
    │ timestamp    │ 8 bytes/row     │ ~1 byte/row      │ ~88% (delta)   │
    │ open         │ 8 bytes/row     │ ~2 bytes/row     │ ~75% (gorilla) │
    │ high         │ 8 bytes/row     │ ~1 byte/row      │ ~88% (gorilla) │
    │ low          │ 8 bytes/row     │ ~1 byte/row      │ ~88% (gorilla) │
    │ close        │ 8 bytes/row     │ ~2 bytes/row     │ ~75% (gorilla) │
    │ volume       │ 8 bytes/row     │ ~2 bytes/row     │ ~75% (delta)   │
    └──────────────┴─────────────────┴──────────────────┴────────────────┘
```

### Retention Policies

```sql
-- Optional: Auto-delete data older than retention period
-- Uncomment based on business requirements

-- Keep 5 years of bar data
SELECT add_retention_policy('bars', INTERVAL '5 years');

-- Keep 30 days of quote data (high volume, less historical value)
SELECT add_retention_policy('quotes', INTERVAL '30 days');

-- Keep 7 days of trade data (tick level, very high volume)
SELECT add_retention_policy('trades', INTERVAL '7 days');


-- Manually drop old data (alternative to policy)
SELECT drop_chunks('bars', older_than => INTERVAL '5 years');
```

---

## Cost Analysis

### Detailed Cost Breakdown

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     COST COMPARISON: MVP vs FULL SOLUTION                   │
└─────────────────────────────────────────────────────────────────────────────┘


                              MVP (Redis Cache)
    ┌─────────────────────────────────────────────────────────────────────┐
    │                                                                     │
    │   Infrastructure:                                                   │
    │   ├── Redis (existing): +1 GB memory             ~$15/month         │
    │   └── No additional compute                      $0                 │
    │                                                                     │
    │   Data Provider:                                                    │
    │   └── Alpaca Free Tier                           $0                 │
    │                                                                     │
    │   ────────────────────────────────────────────────────────────────  │
    │   TOTAL:                                         ~$15/month         │
    │                                                                     │
    │   Limitations:                                                      │
    │   • Rate-limited API calls                                          │
    │   • No historical data beyond cache TTL                             │
    │   • Backtests fetch data each run                                   │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘


                         FULL SOLUTION (TimescaleDB)
    ┌─────────────────────────────────────────────────────────────────────┐
    │                                                                     │
    │   OPTION A: Timescale Cloud (Managed)                               │
    │   ├── Compute: 4 vCPU, 16 GB RAM                 ~$90/month         │
    │   ├── Storage: 100 GB SSD                        ~$20/month         │
    │   ├── Backup: Included                           $0                 │
    │   └── High Availability: +50%                    ~$55/month         │
    │                                                                     │
    │   Data Provider:                                                    │
    │   └── Alpaca Algo Trader Plus                    $99/month          │
    │       (unlimited historical data)                                   │
    │                                                                     │
    │   ────────────────────────────────────────────────────────────────  │
    │   TOTAL (without HA):                            ~$209/month        │
    │   TOTAL (with HA):                               ~$264/month        │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────┐
    │                                                                     │
    │   OPTION B: Self-Hosted on GKE                                      │
    │   ├── GKE Node: e2-standard-4 (4 vCPU, 16 GB)    ~$100/month        │
    │   ├── Persistent Disk: 100 GB SSD                ~$17/month         │
    │   ├── Backup Storage: 50 GB                      ~$5/month          │
    │   └── Ops/Maintenance overhead                   ~$50/month*        │
    │       (*engineer time for upgrades, monitoring)                     │
    │                                                                     │
    │   Data Provider:                                                    │
    │   └── Alpaca Algo Trader Plus                    $99/month          │
    │                                                                     │
    │   ────────────────────────────────────────────────────────────────  │
    │   TOTAL:                                         ~$271/month        │
    │                                                                     │
    │   Note: Lower cloud cost but higher ops burden                      │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘


                           COST PER BACKTEST
    ┌─────────────────────────────────────────────────────────────────────┐
    │                                                                     │
    │   MVP (Redis):                                                      │
    │   • Cache miss: ~500ms API call + rate limit risk                   │
    │   • Cache hit: ~5ms                                                 │
    │   • Cost: API calls count against rate limits                       │
    │                                                                     │
    │   Full Solution (TimescaleDB):                                      │
    │   • Always: ~50ms local query                                       │
    │   • No rate limit concerns                                          │
    │   • Fixed monthly cost regardless of usage                          │
    │                                                                     │
    │   Break-even point:                                                 │
    │   If running >50 backtests/day, TimescaleDB pays for itself         │
    │   in developer time saved waiting for data                          │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘
```

### When to Upgrade

```
    DECISION MATRIX: When to move from MVP to Full Solution

    ┌───────────────────────────────────────────────────────────────────┐
    │                                                                   │
    │   Stay with MVP if:                                               │
    │   ✓ <50 backtests per day                                         │
    │   ✓ Most backtests use same symbols (good cache hit rate)         │
    │   ✓ Not hitting Alpaca rate limits                                │
    │   ✓ No need for historical analysis features                      │
    │                                                                   │
    │   ─────────────────────────────────────────────────────────────   │
    │                                                                   │
    │   Upgrade to TimescaleDB if:                                      │
    │   ✗ >50 backtests per day                                         │
    │   ✗ Users backtest many different symbols (cache misses)          │
    │   ✗ Hitting Alpaca rate limits frequently                         │
    │   ✗ Need to offer historical analysis features                    │
    │   ✗ Want to support longer backtest periods (5+ years)            │
    │   ✗ Planning to add market-wide analysis features                 │
    │                                                                   │
    └───────────────────────────────────────────────────────────────────┘
```

---

## Migration Path

### From MVP to TimescaleDB

```
                         MIGRATION TIMELINE

    Week 1: Infrastructure
    ───────────────────────────────────────────────────────────────────
    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │  Provision  │     │  Install    │     │   Create    │
    │  TimescaleDB│────▶│  Extension  │────▶│  Hypertables│
    │  Instance   │     │             │     │  & Indexes  │
    └─────────────┘     └─────────────┘     └─────────────┘


    Week 2: Backfill
    ───────────────────────────────────────────────────────────────────
    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │   Deploy    │     │    Run      │     │   Verify    │
    │  Backfill   │────▶│  Backfill   │────▶│   Data      │
    │   Worker    │     │  (3-5 days) │     │  Integrity  │
    └─────────────┘     └─────────────┘     └─────────────┘


    Week 3: Integration
    ───────────────────────────────────────────────────────────────────
    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │  Update     │     │   Deploy    │     │   Monitor   │
    │  Services   │────▶│   Daily     │────▶│   & Tune    │
    │  to use DB  │     │   Sync      │     │             │
    └─────────────┘     └─────────────┘     └─────────────┘


    Week 4: Streaming (Optional)
    ───────────────────────────────────────────────────────────────────
    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │   Deploy    │     │  Connect    │     │   Verify    │
    │  Realtime   │────▶│  Alpaca     │────▶│  End-to-End │
    │  Streamer   │     │  WebSocket  │     │             │
    └─────────────┘     └─────────────┘     └─────────────┘
```

### Code Changes Required

```python
# services/market-data/src/services/market_data_service.py

from datetime import datetime
from typing import Protocol

from llamatrade_db.models.market_data import Bar


class MarketDataRepository(Protocol):
    """Abstract interface for market data storage."""

    async def get_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1min",
    ) -> list[Bar]:
        ...

    async def get_latest_bar(self, symbol: str) -> Bar | None:
        ...


class RedisMarketDataRepository:
    """MVP: Redis-backed repository with Alpaca fallback."""

    async def get_bars(self, symbol: str, start: datetime, end: datetime, timeframe: str) -> list[Bar]:
        # Check Redis cache
        # If miss, fetch from Alpaca and cache
        pass


class TimescaleMarketDataRepository:
    """Full: TimescaleDB-backed repository."""

    async def get_bars(self, symbol: str, start: datetime, end: datetime, timeframe: str) -> list[Bar]:
        # Query appropriate continuous aggregate based on timeframe
        # bars -> bars_5m -> bars_1h -> bars_1d
        pass


# Factory function based on config
def get_market_data_repository() -> MarketDataRepository:
    if settings.USE_TIMESCALEDB:
        return TimescaleMarketDataRepository()
    return RedisMarketDataRepository()
```

---

## Operational Runbook

### Monitoring Queries

```sql
-- Check hypertable size and compression ratio
SELECT
    hypertable_name,
    pg_size_pretty(before_compression_total_bytes) as before,
    pg_size_pretty(after_compression_total_bytes) as after,
    round(100 - (after_compression_total_bytes::numeric /
                 before_compression_total_bytes::numeric * 100), 1) as compression_pct
FROM timescaledb_information.hypertable_compression_stats;

-- Check chunk status
SELECT
    hypertable_name,
    chunk_name,
    range_start,
    range_end,
    is_compressed
FROM timescaledb_information.chunks
WHERE hypertable_name = 'bars'
ORDER BY range_start DESC
LIMIT 20;

-- Check continuous aggregate freshness
SELECT
    view_name,
    completed_threshold,
    invalidation_threshold
FROM timescaledb_information.continuous_aggregate_stats;

-- Find slow queries
SELECT
    query,
    calls,
    mean_exec_time,
    total_exec_time
FROM pg_stat_statements
WHERE query LIKE '%bars%'
ORDER BY mean_exec_time DESC
LIMIT 10;
```

### Common Operations

```sql
-- Manually compress a chunk
SELECT compress_chunk('_timescaledb_internal._hyper_1_1_chunk');

-- Decompress for updates (if needed)
SELECT decompress_chunk('_timescaledb_internal._hyper_1_1_chunk');

-- Refresh continuous aggregate manually
CALL refresh_continuous_aggregate('bars_1d', '2024-01-01', '2024-01-31');

-- Check for gaps in data
SELECT
    symbol,
    date_trunc('day', timestamp) as day,
    count(*) as bar_count
FROM bars
WHERE symbol = 'AAPL'
  AND timestamp >= '2024-01-01'
GROUP BY symbol, date_trunc('day', timestamp)
HAVING count(*) < 390  -- Expected bars per day
ORDER BY day;
```

### Backup Strategy

```bash
# Daily backup script (run via cron)
#!/bin/bash

BACKUP_DIR="/backups/timescaledb"
DATE=$(date +%Y%m%d)

# Full backup using pg_dump with TimescaleDB extension
pg_dump -Fc \
    --no-owner \
    --no-acl \
    -h $PGHOST \
    -U $PGUSER \
    -d llamatrade \
    > "$BACKUP_DIR/llamatrade_$DATE.dump"

# Keep last 7 daily backups
find $BACKUP_DIR -name "*.dump" -mtime +7 -delete

# Weekly: also backup to GCS
if [ $(date +%u) -eq 7 ]; then
    gsutil cp "$BACKUP_DIR/llamatrade_$DATE.dump" \
        gs://llamatrade-backups/timescaledb/
fi
```

---

## Summary

TimescaleDB transforms market data storage from a scaling problem into a solved problem:

| Challenge               | TimescaleDB Solution                    |
| ----------------------- | --------------------------------------- |
| 784M rows/year          | Automatic chunking, chunk exclusion     |
| 80 GB raw data          | 8 GB after compression (90%+)           |
| Slow time-range queries | Hypertable indexes, chunk skipping      |
| Multiple timeframes     | Continuous aggregates (auto-maintained) |
| Data retention          | Built-in retention policies             |
| Operational overhead    | Managed service option available        |

**When you're ready to implement:**

1. Start with Timescale Cloud (managed) to minimize ops burden
2. Run backfill worker for 3-5 days to populate historical data
3. Switch services from Redis to TimescaleDB repository
4. Add real-time streaming if needed for live trading

The architecture is designed for a clean migration path from the MVP Redis solution.
