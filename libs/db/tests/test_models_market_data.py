"""Tests for llamatrade_db.models.market_data module."""

from llamatrade_db.models.market_data import (
    Bar,
    Quote,
    Trade,
)


class TestBar:
    """Tests for Bar model."""

    def test_bar_tablename(self) -> None:
        """Test Bar has correct tablename."""
        assert Bar.__tablename__ == "bars"

    def test_bar_has_required_columns(self) -> None:
        """Test Bar has all required columns."""
        columns = Bar.__table__.columns
        assert "id" in columns
        assert "timestamp" in columns
        assert "symbol" in columns
        assert "timeframe" in columns
        assert "open" in columns
        assert "high" in columns
        assert "low" in columns
        assert "close" in columns
        assert "volume" in columns

    def test_bar_has_optional_columns(self) -> None:
        """Test Bar has optional columns."""
        columns = Bar.__table__.columns
        assert "vwap" in columns
        assert "trade_count" in columns

    def test_bar_symbol_not_nullable(self) -> None:
        """Test symbol column is not nullable."""
        col = Bar.__table__.columns["symbol"]
        assert col.nullable is False

    def test_bar_timeframe_not_nullable(self) -> None:
        """Test timeframe column is not nullable."""
        col = Bar.__table__.columns["timeframe"]
        assert col.nullable is False

    def test_bar_timestamp_not_nullable(self) -> None:
        """Test timestamp column is not nullable."""
        col = Bar.__table__.columns["timestamp"]
        assert col.nullable is False

    def test_bar_ohlc_not_nullable(self) -> None:
        """Test OHLC columns are not nullable."""
        columns = Bar.__table__.columns
        assert columns["open"].nullable is False
        assert columns["high"].nullable is False
        assert columns["low"].nullable is False
        assert columns["close"].nullable is False

    def test_bar_volume_not_nullable(self) -> None:
        """Test volume column is not nullable."""
        col = Bar.__table__.columns["volume"]
        assert col.nullable is False

    def test_bar_vwap_nullable(self) -> None:
        """Test vwap is nullable."""
        col = Bar.__table__.columns["vwap"]
        assert col.nullable is True

    def test_bar_trade_count_nullable(self) -> None:
        """Test trade_count is nullable."""
        col = Bar.__table__.columns["trade_count"]
        assert col.nullable is True

    def test_bar_has_composite_primary_key(self) -> None:
        """Test Bar has composite primary key (id, timestamp) for partitioning."""
        pk_columns = [col.name for col in Bar.__table__.primary_key.columns]
        assert "id" in pk_columns
        assert "timestamp" in pk_columns

    def test_bar_has_indexes(self) -> None:
        """Test Bar has expected indexes."""
        table_args = Bar.__table_args__
        assert table_args is not None
        from sqlalchemy import Index

        indexes = [arg for arg in table_args if isinstance(arg, Index)]
        assert len(indexes) >= 2

    def test_bar_has_partition_config(self) -> None:
        """Test Bar has PostgreSQL partition configuration."""
        table_args = Bar.__table_args__
        dict_args = [arg for arg in table_args if isinstance(arg, dict)]
        assert len(dict_args) == 1
        assert dict_args[0].get("postgresql_partition_by") == "RANGE (timestamp)"

    def test_bar_not_tenant_scoped(self) -> None:
        """Test Bar is not tenant-scoped (shared market data)."""
        columns = Bar.__table__.columns
        assert "tenant_id" not in columns


class TestQuote:
    """Tests for Quote model."""

    def test_quote_tablename(self) -> None:
        """Test Quote has correct tablename."""
        assert Quote.__tablename__ == "quotes"

    def test_quote_has_required_columns(self) -> None:
        """Test Quote has all required columns."""
        columns = Quote.__table__.columns
        assert "id" in columns
        assert "timestamp" in columns
        assert "symbol" in columns
        assert "bid_price" in columns
        assert "bid_size" in columns
        assert "ask_price" in columns
        assert "ask_size" in columns

    def test_quote_has_optional_columns(self) -> None:
        """Test Quote has optional columns."""
        columns = Quote.__table__.columns
        assert "bid_exchange" in columns
        assert "ask_exchange" in columns
        assert "conditions" in columns

    def test_quote_symbol_not_nullable(self) -> None:
        """Test symbol column is not nullable."""
        col = Quote.__table__.columns["symbol"]
        assert col.nullable is False

    def test_quote_timestamp_not_nullable(self) -> None:
        """Test timestamp column is not nullable."""
        col = Quote.__table__.columns["timestamp"]
        assert col.nullable is False

    def test_quote_bid_price_not_nullable(self) -> None:
        """Test bid_price column is not nullable."""
        col = Quote.__table__.columns["bid_price"]
        assert col.nullable is False

    def test_quote_ask_price_not_nullable(self) -> None:
        """Test ask_price column is not nullable."""
        col = Quote.__table__.columns["ask_price"]
        assert col.nullable is False

    def test_quote_bid_size_not_nullable(self) -> None:
        """Test bid_size column is not nullable."""
        col = Quote.__table__.columns["bid_size"]
        assert col.nullable is False

    def test_quote_ask_size_not_nullable(self) -> None:
        """Test ask_size column is not nullable."""
        col = Quote.__table__.columns["ask_size"]
        assert col.nullable is False

    def test_quote_exchange_columns_nullable(self) -> None:
        """Test exchange columns are nullable."""
        columns = Quote.__table__.columns
        assert columns["bid_exchange"].nullable is True
        assert columns["ask_exchange"].nullable is True

    def test_quote_conditions_nullable(self) -> None:
        """Test conditions is nullable."""
        col = Quote.__table__.columns["conditions"]
        assert col.nullable is True

    def test_quote_has_composite_primary_key(self) -> None:
        """Test Quote has composite primary key (id, timestamp) for partitioning."""
        pk_columns = [col.name for col in Quote.__table__.primary_key.columns]
        assert "id" in pk_columns
        assert "timestamp" in pk_columns

    def test_quote_has_indexes(self) -> None:
        """Test Quote has expected indexes."""
        table_args = Quote.__table_args__
        assert table_args is not None
        from sqlalchemy import Index

        indexes = [arg for arg in table_args if isinstance(arg, Index)]
        assert len(indexes) >= 1

    def test_quote_has_partition_config(self) -> None:
        """Test Quote has PostgreSQL partition configuration."""
        table_args = Quote.__table_args__
        dict_args = [arg for arg in table_args if isinstance(arg, dict)]
        assert len(dict_args) == 1
        assert dict_args[0].get("postgresql_partition_by") == "RANGE (timestamp)"

    def test_quote_not_tenant_scoped(self) -> None:
        """Test Quote is not tenant-scoped (shared market data)."""
        columns = Quote.__table__.columns
        assert "tenant_id" not in columns


class TestTrade:
    """Tests for Trade model."""

    def test_trade_tablename(self) -> None:
        """Test Trade has correct tablename."""
        assert Trade.__tablename__ == "trades"

    def test_trade_has_required_columns(self) -> None:
        """Test Trade has all required columns."""
        columns = Trade.__table__.columns
        assert "id" in columns
        assert "timestamp" in columns
        assert "symbol" in columns
        assert "price" in columns
        assert "size" in columns

    def test_trade_has_optional_columns(self) -> None:
        """Test Trade has optional columns."""
        columns = Trade.__table__.columns
        assert "exchange" in columns
        assert "trade_id" in columns
        assert "conditions" in columns
        assert "tape" in columns

    def test_trade_symbol_not_nullable(self) -> None:
        """Test symbol column is not nullable."""
        col = Trade.__table__.columns["symbol"]
        assert col.nullable is False

    def test_trade_timestamp_not_nullable(self) -> None:
        """Test timestamp column is not nullable."""
        col = Trade.__table__.columns["timestamp"]
        assert col.nullable is False

    def test_trade_price_not_nullable(self) -> None:
        """Test price column is not nullable."""
        col = Trade.__table__.columns["price"]
        assert col.nullable is False

    def test_trade_size_not_nullable(self) -> None:
        """Test size column is not nullable."""
        col = Trade.__table__.columns["size"]
        assert col.nullable is False

    def test_trade_exchange_nullable(self) -> None:
        """Test exchange is nullable."""
        col = Trade.__table__.columns["exchange"]
        assert col.nullable is True

    def test_trade_trade_id_nullable(self) -> None:
        """Test trade_id is nullable."""
        col = Trade.__table__.columns["trade_id"]
        assert col.nullable is True

    def test_trade_conditions_nullable(self) -> None:
        """Test conditions is nullable."""
        col = Trade.__table__.columns["conditions"]
        assert col.nullable is True

    def test_trade_tape_nullable(self) -> None:
        """Test tape is nullable."""
        col = Trade.__table__.columns["tape"]
        assert col.nullable is True

    def test_trade_has_composite_primary_key(self) -> None:
        """Test Trade has composite primary key (id, timestamp) for partitioning."""
        pk_columns = [col.name for col in Trade.__table__.primary_key.columns]
        assert "id" in pk_columns
        assert "timestamp" in pk_columns

    def test_trade_has_indexes(self) -> None:
        """Test Trade has expected indexes."""
        table_args = Trade.__table_args__
        assert table_args is not None
        from sqlalchemy import Index

        indexes = [arg for arg in table_args if isinstance(arg, Index)]
        assert len(indexes) >= 1

    def test_trade_has_partition_config(self) -> None:
        """Test Trade has PostgreSQL partition configuration."""
        table_args = Trade.__table_args__
        dict_args = [arg for arg in table_args if isinstance(arg, dict)]
        assert len(dict_args) == 1
        assert dict_args[0].get("postgresql_partition_by") == "RANGE (timestamp)"

    def test_trade_not_tenant_scoped(self) -> None:
        """Test Trade is not tenant-scoped (shared market data)."""
        columns = Trade.__table__.columns
        assert "tenant_id" not in columns
