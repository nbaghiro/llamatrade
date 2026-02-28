"""Strategy adapter for backtest engine.

Adapts compiled DSL strategies to work with the BacktestEngine,
converting Signal outputs to SignalData format.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from llamatrade_dsl import INDICATORS, parse_strategy, validate_strategy
from llamatrade_dsl.ast import ASTNode, FunctionCall, Keyword, Literal, Symbol

from src.engine.backtester import BacktestEngine, BarData, SignalData


@dataclass(frozen=True)
class IndicatorSpec:
    """Specification for an indicator to compute."""

    indicator_type: str
    source: str
    params: tuple[int | float, ...]
    output_key: str
    output_field: str | None
    required_bars: int


@dataclass
class StrategyState:
    """Mutable state for strategy evaluation."""

    bar_history: list[BarData] = field(default_factory=list)
    indicators: dict[str, np.ndarray] = field(default_factory=dict)
    position_side: str | None = None
    position_entry_price: float = 0.0


def _extract_indicators(node: ASTNode, specs: dict[str, IndicatorSpec]) -> None:
    """Recursively extract indicator specs from an AST node."""
    if not isinstance(node, FunctionCall):
        return

    if node.name in INDICATORS:
        # Extract indicator parameters
        source = "close"
        params: list[int | float] = []
        output_field: str | None = None

        for arg in node.args:
            if isinstance(arg, Symbol):
                source = arg.name
            elif isinstance(arg, Literal) and isinstance(arg.value, (int, float)):
                params.append(arg.value)
            elif isinstance(arg, Keyword):
                output_field = arg.name

        # Generate output key
        parts = [node.name, source] + [str(p) for p in params]
        if output_field:
            parts.append(output_field)
        output_key = "_".join(parts)

        if output_key not in specs:
            # Calculate required bars
            required_bars = int(params[0]) if params else 14
            specs[output_key] = IndicatorSpec(
                indicator_type=node.name,
                source=source,
                params=tuple(params),
                output_key=output_key,
                output_field=output_field,
                required_bars=required_bars,
            )

    # Recurse into arguments
    for arg in node.args:
        _extract_indicators(arg, specs)


def _compute_sma(values: np.ndarray, period: int) -> np.ndarray:
    """Simple Moving Average."""
    if len(values) < period:
        return np.full(len(values), np.nan)
    result = np.full(len(values), np.nan)
    cumsum = np.cumsum(values)
    result[period - 1 :] = (cumsum[period - 1 :] - np.concatenate([[0], cumsum[:-period]])) / period
    return result


def _compute_ema(values: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average."""
    if len(values) < period:
        return np.full(len(values), np.nan)
    result = np.full(len(values), np.nan)
    multiplier = 2.0 / (period + 1)
    result[period - 1] = np.mean(values[:period])
    for i in range(period, len(values)):
        result[i] = (values[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


def _compute_rsi(values: np.ndarray, period: int) -> np.ndarray:
    """Relative Strength Index."""
    if len(values) < period + 1:
        return np.full(len(values), np.nan)

    deltas = np.diff(values)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    result = np.full(len(values), np.nan)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return result


def _compute_stddev(values: np.ndarray, period: int) -> np.ndarray:
    """Standard Deviation."""
    if len(values) < period:
        return np.full(len(values), np.nan)
    result = np.full(len(values), np.nan)
    for i in range(period - 1, len(values)):
        result[i] = np.std(values[i - period + 1 : i + 1], ddof=0)
    return result


def _compute_momentum(values: np.ndarray, period: int) -> np.ndarray:
    """Momentum: current price - price n periods ago."""
    if len(values) < period:
        return np.full(len(values), np.nan)
    result = np.full(len(values), np.nan)
    result[period:] = values[period:] - values[:-period]
    return result


def _compute_macd(
    values: np.ndarray, fast: int, slow: int, signal: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MACD: returns (macd_line, signal_line, histogram)."""
    ema_fast = _compute_ema(values, fast)
    ema_slow = _compute_ema(values, slow)
    macd_line = ema_fast - ema_slow

    # Signal line is EMA of MACD line
    signal_line = np.full(len(values), np.nan)
    # Start calculating signal from where MACD is valid
    start_idx = slow - 1
    if len(values) > start_idx + signal:
        valid_macd = macd_line[start_idx:]
        signal_ema = _compute_ema(valid_macd, signal)
        signal_line[start_idx:] = signal_ema

    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _compute_bbands(
    values: np.ndarray, period: int, num_std: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands: returns (upper, middle, lower)."""
    middle = _compute_sma(values, period)
    stddev = _compute_stddev(values, period)
    upper = middle + num_std * stddev
    lower = middle - num_std * stddev
    return upper, middle, lower


def _compute_true_range(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> np.ndarray:
    """True Range calculation."""
    n = len(highs)
    if n < 2:
        return np.full(n, np.nan)

    tr = np.full(n, np.nan)
    tr[0] = highs[0] - lows[0]

    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)

    return tr


def _compute_atr(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int
) -> np.ndarray:
    """Average True Range."""
    tr = _compute_true_range(highs, lows, closes)
    return _compute_ema(tr, period)


def _compute_adx(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """ADX: returns (adx, plus_di, minus_di)."""
    n = len(highs)
    if n < period + 1:
        return (
            np.full(n, np.nan),
            np.full(n, np.nan),
            np.full(n, np.nan),
        )

    tr = _compute_true_range(highs, lows, closes)

    # Calculate +DM and -DM
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)

    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]

        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move

    # Smooth TR, +DM, -DM using Wilder's smoothing
    atr = _compute_ema(tr, period)
    smoothed_plus_dm = _compute_ema(plus_dm, period)
    smoothed_minus_dm = _compute_ema(minus_dm, period)

    # Calculate +DI and -DI
    plus_di = np.full(n, np.nan)
    minus_di = np.full(n, np.nan)

    valid = atr > 0
    plus_di[valid] = 100 * smoothed_plus_dm[valid] / atr[valid]
    minus_di[valid] = 100 * smoothed_minus_dm[valid] / atr[valid]

    # Calculate DX
    dx = np.full(n, np.nan)
    di_sum = plus_di + minus_di
    di_diff = np.abs(plus_di - minus_di)
    valid = di_sum > 0
    dx[valid] = 100 * di_diff[valid] / di_sum[valid]

    # ADX is smoothed DX
    adx = _compute_ema(dx, period)

    return adx, plus_di, minus_di


def _compute_stochastic(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, k_period: int, d_period: int
) -> tuple[np.ndarray, np.ndarray]:
    """Stochastic Oscillator: returns (%K, %D)."""
    n = len(closes)
    if n < k_period:
        return np.full(n, np.nan), np.full(n, np.nan)

    k = np.full(n, np.nan)

    for i in range(k_period - 1, n):
        high_max = np.max(highs[i - k_period + 1 : i + 1])
        low_min = np.min(lows[i - k_period + 1 : i + 1])
        if high_max - low_min > 0:
            k[i] = 100 * (closes[i] - low_min) / (high_max - low_min)
        else:
            k[i] = 50  # Midpoint if no range

    # %D is SMA of %K
    d = _compute_sma(k, d_period)
    return k, d


def _compute_cci(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int
) -> np.ndarray:
    """Commodity Channel Index."""
    n = len(closes)
    if n < period:
        return np.full(n, np.nan)

    # Typical price
    tp = (highs + lows + closes) / 3

    result = np.full(n, np.nan)
    for i in range(period - 1, n):
        window = tp[i - period + 1 : i + 1]
        sma = np.mean(window)
        mean_dev = np.mean(np.abs(window - sma))
        if mean_dev > 0:
            result[i] = (tp[i] - sma) / (0.015 * mean_dev)
        else:
            result[i] = 0

    return result


def _compute_williams_r(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int
) -> np.ndarray:
    """Williams %R."""
    n = len(closes)
    if n < period:
        return np.full(n, np.nan)

    result = np.full(n, np.nan)
    for i in range(period - 1, n):
        high_max = np.max(highs[i - period + 1 : i + 1])
        low_min = np.min(lows[i - period + 1 : i + 1])
        if high_max - low_min > 0:
            result[i] = -100 * (high_max - closes[i]) / (high_max - low_min)
        else:
            result[i] = -50  # Midpoint if no range

    return result


def _compute_obv(closes: np.ndarray, volumes: np.ndarray) -> np.ndarray:
    """On-Balance Volume."""
    n = len(closes)
    if n < 2:
        return np.full(n, np.nan)

    result = np.zeros(n)
    result[0] = volumes[0]

    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            result[i] = result[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            result[i] = result[i - 1] - volumes[i]
        else:
            result[i] = result[i - 1]

    return result


def _compute_mfi(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    period: int,
) -> np.ndarray:
    """Money Flow Index."""
    n = len(closes)
    if n < period + 1:
        return np.full(n, np.nan)

    # Typical price and raw money flow
    tp = (highs + lows + closes) / 3
    raw_mf = tp * volumes

    result = np.full(n, np.nan)

    for i in range(period, n):
        positive_mf = 0.0
        negative_mf = 0.0

        for j in range(i - period + 1, i + 1):
            if tp[j] > tp[j - 1]:
                positive_mf += raw_mf[j]
            elif tp[j] < tp[j - 1]:
                negative_mf += raw_mf[j]

        if negative_mf > 0:
            mf_ratio = positive_mf / negative_mf
            result[i] = 100 - (100 / (1 + mf_ratio))
        else:
            result[i] = 100 if positive_mf > 0 else 50

    return result


def _compute_vwap(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, volumes: np.ndarray
) -> np.ndarray:
    """Volume Weighted Average Price (cumulative)."""
    n = len(closes)
    if n < 1:
        return np.full(n, np.nan)

    # Typical price
    tp = (highs + lows + closes) / 3

    cum_tp_vol = np.cumsum(tp * volumes)
    cum_vol = np.cumsum(volumes)

    result = np.full(n, np.nan)
    valid = cum_vol > 0
    result[valid] = cum_tp_vol[valid] / cum_vol[valid]

    return result


def _compute_keltner(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int,
    multiplier: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Keltner Channel: returns (upper, middle, lower)."""
    middle = _compute_ema(closes, period)
    atr = _compute_atr(highs, lows, closes, period)
    upper = middle + multiplier * atr
    lower = middle - multiplier * atr
    return upper, middle, lower


def _compute_donchian(
    highs: np.ndarray, lows: np.ndarray, period: int
) -> tuple[np.ndarray, np.ndarray]:
    """Donchian Channel: returns (upper, lower)."""
    n = len(highs)
    if n < period:
        return np.full(n, np.nan), np.full(n, np.nan)

    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)

    for i in range(period - 1, n):
        upper[i] = np.max(highs[i - period + 1 : i + 1])
        lower[i] = np.min(lows[i - period + 1 : i + 1])

    return upper, lower


def _compute_indicator(
    spec: IndicatorSpec,
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    volumes: np.ndarray,
) -> np.ndarray:
    """Compute a single indicator."""
    source_data = closes
    if spec.source == "high":
        source_data = highs
    elif spec.source == "low":
        source_data = lows
    elif spec.source == "volume":
        source_data = volumes.astype(float)

    period = int(spec.params[0]) if spec.params else 14
    output_field = spec.output_field

    # Simple single-output indicators
    if spec.indicator_type == "sma":
        return _compute_sma(source_data, period)
    elif spec.indicator_type == "ema":
        return _compute_ema(source_data, period)
    elif spec.indicator_type == "rsi":
        return _compute_rsi(source_data, period)
    elif spec.indicator_type == "stddev":
        return _compute_stddev(source_data, period)
    elif spec.indicator_type == "momentum":
        return _compute_momentum(source_data, period)

    # MACD: (fast, slow, signal) periods, outputs: line, signal, histogram
    elif spec.indicator_type == "macd":
        fast = int(spec.params[0]) if len(spec.params) > 0 else 12
        slow = int(spec.params[1]) if len(spec.params) > 1 else 26
        signal = int(spec.params[2]) if len(spec.params) > 2 else 9
        macd_line, signal_line, histogram = _compute_macd(source_data, fast, slow, signal)
        if output_field == "signal":
            return signal_line
        elif output_field == "histogram":
            return histogram
        else:  # "line" or default
            return macd_line

    # Bollinger Bands: (period, num_std), outputs: upper, middle, lower
    elif spec.indicator_type == "bbands":
        num_std = float(spec.params[1]) if len(spec.params) > 1 else 2.0
        upper, middle, lower = _compute_bbands(source_data, period, num_std)
        if output_field == "upper":
            return upper
        elif output_field == "lower":
            return lower
        else:  # "middle" or default
            return middle

    # ATR: (period)
    elif spec.indicator_type == "atr":
        return _compute_atr(highs, lows, closes, period)

    # ADX: (period), outputs: value, plus_di, minus_di
    elif spec.indicator_type == "adx":
        adx, plus_di, minus_di = _compute_adx(highs, lows, closes, period)
        if output_field == "plus_di":
            return plus_di
        elif output_field == "minus_di":
            return minus_di
        else:  # "value" or default
            return adx

    # Stochastic: (k_period, d_period), outputs: k, d
    elif spec.indicator_type == "stoch":
        k_period = int(spec.params[0]) if len(spec.params) > 0 else 14
        d_period = int(spec.params[1]) if len(spec.params) > 1 else 3
        k, d = _compute_stochastic(highs, lows, closes, k_period, d_period)
        if output_field == "d":
            return d
        else:  # "k" or default
            return k

    # CCI: (period)
    elif spec.indicator_type == "cci":
        return _compute_cci(highs, lows, closes, period)

    # Williams %R: (period)
    elif spec.indicator_type == "williams-r":
        return _compute_williams_r(highs, lows, closes, period)

    # OBV: no period
    elif spec.indicator_type == "obv":
        return _compute_obv(closes, volumes.astype(float))

    # MFI: (period)
    elif spec.indicator_type == "mfi":
        return _compute_mfi(highs, lows, closes, volumes.astype(float), period)

    # VWAP: no period (cumulative)
    elif spec.indicator_type == "vwap":
        return _compute_vwap(highs, lows, closes, volumes.astype(float))

    # Keltner Channel: (period, multiplier), outputs: upper, middle, lower
    elif spec.indicator_type == "keltner":
        multiplier = float(spec.params[1]) if len(spec.params) > 1 else 2.0
        upper, middle, lower = _compute_keltner(highs, lows, closes, period, multiplier)
        if output_field == "upper":
            return upper
        elif output_field == "lower":
            return lower
        else:  # "middle" or default
            return middle

    # Donchian Channel: (period), outputs: upper, lower
    elif spec.indicator_type == "donchian":
        upper, lower = _compute_donchian(highs, lows, period)
        if output_field == "lower":
            return lower
        else:  # "upper" or default
            return upper

    else:
        # Fallback to SMA for unsupported indicators
        return _compute_sma(source_data, period)


def _evaluate_condition(
    node: ASTNode,
    indicators: dict[str, np.ndarray],
    current_bar: BarData,
    prev_bar: BarData | None,
    has_position: bool,
) -> bool:
    """Evaluate a condition AST node."""
    if isinstance(node, Literal):
        return bool(node.value)

    if isinstance(node, FunctionCall):
        name = node.name
        args = node.args

        # Logical operators
        if name == "and":
            return all(
                _evaluate_condition(arg, indicators, current_bar, prev_bar, has_position)
                for arg in args
            )
        if name == "or":
            return any(
                _evaluate_condition(arg, indicators, current_bar, prev_bar, has_position)
                for arg in args
            )
        if name == "not":
            return not _evaluate_condition(args[0], indicators, current_bar, prev_bar, has_position)

        # Comparisons
        if name in (">", "<", ">=", "<=", "=", "!="):
            left = _get_value(args[0], indicators, current_bar)
            right = _get_value(args[1], indicators, current_bar)
            if name == ">":
                return left > right
            if name == "<":
                return left < right
            if name == ">=":
                return left >= right
            if name == "<=":
                return left <= right
            if name == "=":
                return left == right
            if name == "!=":
                return left != right

        # Crossovers
        if name in ("cross-above", "cross-below"):
            if prev_bar is None:
                return False
            curr_left = _get_value(args[0], indicators, current_bar)
            curr_right = _get_value(args[1], indicators, current_bar)
            prev_left = _get_value(args[0], indicators, current_bar, offset=1)
            prev_right = _get_value(args[1], indicators, current_bar, offset=1)

            if name == "cross-above":
                return prev_left <= prev_right and curr_left > curr_right
            else:
                return prev_left >= prev_right and curr_left < curr_right

        # Special functions
        if name == "has-position":
            return has_position

    return False


def _get_value(
    node: ASTNode,
    indicators: dict[str, np.ndarray],
    current_bar: BarData,
    offset: int = 0,
) -> float:
    """Get the numeric value of an AST node."""
    if isinstance(node, Literal):
        return float(node.value) if isinstance(node.value, (int, float)) else 0.0

    if isinstance(node, Symbol):
        if node.name == "close":
            return float(current_bar["close"])
        if node.name == "open":
            return float(current_bar["open"])
        if node.name == "high":
            return float(current_bar["high"])
        if node.name == "low":
            return float(current_bar["low"])
        if node.name == "volume":
            return float(current_bar["volume"])
        return 0.0

    if isinstance(node, FunctionCall):
        if node.name in INDICATORS:
            key = _build_indicator_key(node)
            if key in indicators:
                arr = indicators[key]
                idx = -(offset + 1)
                if -idx <= len(arr):
                    return float(arr[idx])
        return 0.0

    return 0.0


def _build_indicator_key(call: FunctionCall) -> str:
    """Build indicator cache key from function call."""
    parts = [call.name]
    source = "close"
    params: list[str] = []
    output_field: str | None = None

    for arg in call.args:
        if isinstance(arg, Symbol):
            source = arg.name
        elif isinstance(arg, Literal) and isinstance(arg.value, (int, float)):
            params.append(str(arg.value))
        elif isinstance(arg, Keyword):
            output_field = arg.name

    parts.append(source)
    parts.extend(params)
    if output_field:
        parts.append(output_field)

    return "_".join(parts)


def create_strategy_function(
    config_sexpr: str,
) -> tuple[Callable[[BacktestEngine, str, BarData], list[SignalData]], int]:
    """Create a strategy function from an S-expression config.

    Args:
        config_sexpr: The strategy S-expression

    Returns:
        Tuple of (strategy function, minimum required bars)
    """
    # Parse and validate
    strategy = parse_strategy(config_sexpr)
    validation = validate_strategy(strategy)
    if not validation.valid:
        errors = "; ".join(str(e) for e in validation.errors)
        raise ValueError(f"Invalid strategy: {errors}")

    # Extract indicators
    indicator_specs: dict[str, IndicatorSpec] = {}
    _extract_indicators(strategy.entry, indicator_specs)
    _extract_indicators(strategy.exit, indicator_specs)

    # Calculate minimum bars
    min_bars = 2  # At least 2 for crossovers
    for spec in indicator_specs.values():
        min_bars = max(min_bars, spec.required_bars + 1)

    # Create state per symbol
    states: dict[str, StrategyState] = {}

    def strategy_fn(engine: BacktestEngine, symbol: str, bar: BarData) -> list[SignalData]:
        # Get or create state for this symbol
        if symbol not in states:
            states[symbol] = StrategyState()
        state = states[symbol]

        # Add bar to history
        state.bar_history.append(bar)

        # Check if we have enough history
        if len(state.bar_history) < min_bars:
            return []

        # Compute indicators
        closes = np.array([b["close"] for b in state.bar_history])
        highs = np.array([b["high"] for b in state.bar_history])
        lows = np.array([b["low"] for b in state.bar_history])
        volumes = np.array([b["volume"] for b in state.bar_history])

        for key, spec in indicator_specs.items():
            state.indicators[key] = _compute_indicator(spec, closes, highs, lows, volumes)

        # Get previous bar
        prev_bar = state.bar_history[-2] if len(state.bar_history) >= 2 else None

        signals: list[SignalData] = []
        has_position = engine.has_position(symbol)

        # Check entry condition (only if not in position)
        if not has_position:
            if _evaluate_condition(strategy.entry, state.indicators, bar, prev_bar, has_position):
                # Calculate position size
                sizing_value = strategy.sizing.get("value", 10)
                equity = engine.get_equity()
                quantity = (equity * sizing_value / 100) / bar["close"]

                signals.append(
                    {
                        "type": "buy",
                        "symbol": symbol,
                        "quantity": quantity,
                        "price": bar["close"],
                    }
                )
                state.position_side = "long"
                state.position_entry_price = bar["close"]

        # Check exit condition (only if in position)
        else:
            should_exit = _evaluate_condition(
                strategy.exit, state.indicators, bar, prev_bar, has_position
            )

            # Also check risk exits
            if state.position_side == "long" and state.position_entry_price > 0:
                pnl_pct = (
                    (bar["close"] - state.position_entry_price) / state.position_entry_price
                ) * 100

                stop_loss = strategy.risk.get("stop_loss_pct")
                take_profit = strategy.risk.get("take_profit_pct")

                if stop_loss and pnl_pct <= -stop_loss:
                    should_exit = True
                if take_profit and pnl_pct >= take_profit:
                    should_exit = True

            if should_exit:
                pos = engine.get_position(symbol)
                if pos:
                    signals.append(
                        {
                            "type": "sell",
                            "symbol": symbol,
                            "quantity": pos.quantity,
                            "price": bar["close"],
                        }
                    )
                    state.position_side = None
                    state.position_entry_price = 0.0

        return signals

    return strategy_fn, min_bars
