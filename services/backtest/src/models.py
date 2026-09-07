"""Backtest Service - shared request-validation constants.

The request/response DTOs were collapsed onto proto (1A); only the timeframe
vocabulary remains here.
"""

# Valid timeframes; string form mirrors the Timeframe enum in market_data.proto
# (single source of truth). See: libs/proto/llamatrade_proto/protos/market_data.proto
VALID_TIMEFRAMES = ("1Min", "5Min", "15Min", "30Min", "1H", "4H", "1D", "1W")
