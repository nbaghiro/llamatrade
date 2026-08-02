"""Stream bar parsing must carry vwap and trade_count through when Alpaca sends them."""

from llamatrade_alpaca.streaming.market_data_stream import MarketDataStreamClient


def _client() -> MarketDataStreamClient:
    return MarketDataStreamClient(api_key="key", api_secret="secret")


def test_parse_bar_includes_vwap_and_trade_count() -> None:
    payload = {
        "T": "b",
        "S": "SPY",
        "o": 100.0,
        "h": 101.0,
        "l": 99.5,
        "c": 100.5,
        "v": 12345,
        "vw": 100.31,
        "n": 87,
        "t": "2026-07-28T14:30:00Z",
    }
    bar = _client()._parse_bar(payload)
    assert bar is not None
    assert bar["vwap"] == 100.31
    assert bar["trade_count"] == 87


def test_parse_bar_omits_absent_optional_fields() -> None:
    payload = {"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1, "t": "2026-07-28T14:30:00Z"}
    bar = _client()._parse_bar(payload)
    assert bar is not None
    assert "vwap" not in bar
    assert "trade_count" not in bar
