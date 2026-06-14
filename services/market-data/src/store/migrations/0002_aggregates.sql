-- Continuous aggregates: intraday rollups derived from raw minute bars, and
-- weekly/monthly derived from adjusted daily. Each exposes the same column
-- shape as the base tables (time, symbol, OHLCV, vwap, trade_count) so the
-- repository reads them uniformly. Created WITH NO DATA; refresh policies in
-- 0003 backfill + keep them current.
--
-- vwap is recomputed as a volume-weighted average of the source vwap so it
-- stays correct across the bucket rather than averaging the averages.

CREATE MATERIALIZED VIEW IF NOT EXISTS bars_5m WITH (timescaledb.continuous) AS
SELECT time_bucket('5 minutes', time) AS time, symbol, first(open, time) AS open, max(high) AS high, min(low) AS low, last(close, time) AS close, sum(volume) AS volume, sum(vwap * volume) / NULLIF(sum(volume), 0) AS vwap, sum(trade_count) AS trade_count FROM bars_1m GROUP BY 1, 2 WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS bars_15m WITH (timescaledb.continuous) AS
SELECT time_bucket('15 minutes', time) AS time, symbol, first(open, time) AS open, max(high) AS high, min(low) AS low, last(close, time) AS close, sum(volume) AS volume, sum(vwap * volume) / NULLIF(sum(volume), 0) AS vwap, sum(trade_count) AS trade_count FROM bars_1m GROUP BY 1, 2 WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS bars_30m WITH (timescaledb.continuous) AS
SELECT time_bucket('30 minutes', time) AS time, symbol, first(open, time) AS open, max(high) AS high, min(low) AS low, last(close, time) AS close, sum(volume) AS volume, sum(vwap * volume) / NULLIF(sum(volume), 0) AS vwap, sum(trade_count) AS trade_count FROM bars_1m GROUP BY 1, 2 WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS bars_1h WITH (timescaledb.continuous) AS
SELECT time_bucket('1 hour', time) AS time, symbol, first(open, time) AS open, max(high) AS high, min(low) AS low, last(close, time) AS close, sum(volume) AS volume, sum(vwap * volume) / NULLIF(sum(volume), 0) AS vwap, sum(trade_count) AS trade_count FROM bars_1m GROUP BY 1, 2 WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS bars_4h WITH (timescaledb.continuous) AS
SELECT time_bucket('4 hours', time) AS time, symbol, first(open, time) AS open, max(high) AS high, min(low) AS low, last(close, time) AS close, sum(volume) AS volume, sum(vwap * volume) / NULLIF(sum(volume), 0) AS vwap, sum(trade_count) AS trade_count FROM bars_1m GROUP BY 1, 2 WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS bars_1w WITH (timescaledb.continuous) AS
SELECT time_bucket('1 week', time) AS time, symbol, first(open, time) AS open, max(high) AS high, min(low) AS low, last(close, time) AS close, sum(volume) AS volume, sum(vwap * volume) / NULLIF(sum(volume), 0) AS vwap, sum(trade_count) AS trade_count FROM bars_daily GROUP BY 1, 2 WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS bars_1mo WITH (timescaledb.continuous) AS
SELECT time_bucket('1 month', time) AS time, symbol, first(open, time) AS open, max(high) AS high, min(low) AS low, last(close, time) AS close, sum(volume) AS volume, sum(vwap * volume) / NULLIF(sum(volume), 0) AS vwap, sum(trade_count) AS trade_count FROM bars_daily GROUP BY 1, 2 WITH NO DATA;
