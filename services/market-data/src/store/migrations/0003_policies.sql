-- Retention, compression, and continuous-aggregate refresh policies.
-- Tiered by access pattern: raw minute is a hot rolling window (compress early,
-- drop at 90d); intraday aggregates kept ~1y; adjusted daily kept forever
-- (compressed when cold). Windows are intentionally conservative defaults —
-- widen MARKET_DATA retention by editing these in a follow-up migration.

-- Minute: compress cold chunks, drop past the rolling window.
ALTER TABLE bars_1m SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol', timescaledb.compress_orderby = 'time DESC');
SELECT add_compression_policy('bars_1m', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('bars_1m', INTERVAL '90 days', if_not_exists => TRUE);

-- Daily: compress when cold; NO retention policy (kept indefinitely).
ALTER TABLE bars_daily SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol', timescaledb.compress_orderby = 'time DESC');
SELECT add_compression_policy('bars_daily', INTERVAL '90 days', if_not_exists => TRUE);

-- Continuous-aggregate refresh: keep recent buckets current; the start_offset
-- bounds how far back each run recomputes.
SELECT add_continuous_aggregate_policy('bars_5m',  start_offset => INTERVAL '3 days',  end_offset => INTERVAL '1 minute',  schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('bars_15m', start_offset => INTERVAL '7 days',  end_offset => INTERVAL '1 minute',  schedule_interval => INTERVAL '15 minutes', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('bars_30m', start_offset => INTERVAL '14 days', end_offset => INTERVAL '1 minute',  schedule_interval => INTERVAL '30 minutes', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('bars_1h',  start_offset => INTERVAL '30 days', end_offset => INTERVAL '1 minute',  schedule_interval => INTERVAL '1 hour', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('bars_4h',  start_offset => INTERVAL '90 days', end_offset => INTERVAL '1 hour',    schedule_interval => INTERVAL '1 hour', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('bars_1w',  start_offset => INTERVAL '1 year',  end_offset => INTERVAL '1 day',     schedule_interval => INTERVAL '1 day', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('bars_1mo', start_offset => INTERVAL '3 years', end_offset => INTERVAL '1 day',     schedule_interval => INTERVAL '1 day', if_not_exists => TRUE);
