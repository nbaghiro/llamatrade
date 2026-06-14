-- Base bar tables + Timescale hypertables.
-- Statements are applied individually in autocommit (see migrate.py) because
-- create_hypertable / policy functions cannot run inside a wrapping transaction.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Raw minute bars (unadjusted). Unique (symbol, time) includes the partition
-- column, as Timescale requires for unique constraints on hypertables.
CREATE TABLE IF NOT EXISTS bars_1m (
    time         TIMESTAMPTZ      NOT NULL,
    symbol       VARCHAR(20)      NOT NULL,
    open         NUMERIC(18, 8)   NOT NULL,
    high         NUMERIC(18, 8)   NOT NULL,
    low          NUMERIC(18, 8)   NOT NULL,
    close        NUMERIC(18, 8)   NOT NULL,
    volume       BIGINT           NOT NULL,
    vwap         NUMERIC(18, 8),
    trade_count  INTEGER,
    CONSTRAINT uq_bars_1m_symbol_time UNIQUE (symbol, time)
);

SELECT create_hypertable('bars_1m', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS ix_bars_1m_symbol_time ON bars_1m (symbol, time DESC);

-- Official adjusted daily bars. Retained indefinitely; adjustment/fetched_at
-- drive the corporate-action self-heal.
CREATE TABLE IF NOT EXISTS bars_daily (
    time         TIMESTAMPTZ      NOT NULL,
    symbol       VARCHAR(20)      NOT NULL,
    open         NUMERIC(18, 8)   NOT NULL,
    high         NUMERIC(18, 8)   NOT NULL,
    low          NUMERIC(18, 8)   NOT NULL,
    close        NUMERIC(18, 8)   NOT NULL,
    volume       BIGINT           NOT NULL,
    vwap         NUMERIC(18, 8),
    trade_count  INTEGER,
    adjustment   VARCHAR(10)      NOT NULL DEFAULT 'raw',
    fetched_at   TIMESTAMPTZ,
    CONSTRAINT uq_bars_daily_symbol_time UNIQUE (symbol, time)
);

SELECT create_hypertable('bars_daily', 'time', chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS ix_bars_daily_symbol_time ON bars_daily (symbol, time DESC);
