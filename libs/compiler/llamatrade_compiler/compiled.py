"""Compiled allocation strategy for efficient execution.

CompiledStrategy wraps a Strategy AST and provides efficient evaluation
of allocation rules against market data, computing portfolio weights.
"""

from dataclasses import dataclass, field
from typing import TypedDict

import numpy as np
from numpy.typing import NDArray

from llamatrade_compiler.evaluator import evaluate_condition_safe
from llamatrade_compiler.extractor import (
    IndicatorSpec,
    extract_indicators,
    get_max_lookback,
    get_required_symbols,
)
from llamatrade_compiler.pipeline import PriceData, compute_all_indicators
from llamatrade_compiler.state import EvaluationState
from llamatrade_compiler.types import Bar
from llamatrade_dsl import (
    Asset,
    Block,
    Filter,
    Group,
    If,
    Strategy,
    Weight,
)


class Allocation(TypedDict):
    """Portfolio allocation result."""

    weights: dict[str, float]  # symbol -> weight percentage (0-100)
    rebalance_needed: bool
    metadata: dict[str, str | float | int]


def _empty_indicator_list() -> list[IndicatorSpec]:
    """Factory for empty indicator list."""
    return []


def _empty_bar_history() -> dict[str, list[Bar]]:
    """Factory for empty bar history."""
    return {}


def _empty_indicator_cache() -> dict[str, NDArray[np.float64]]:
    """Factory for empty indicator cache."""
    return {}


def _empty_symbol_set() -> set[str]:
    """Factory for empty symbol set."""
    return set()


def _empty_allocation() -> dict[str, float]:
    """Factory for empty allocation dict."""
    return {}


@dataclass
class CompiledStrategy:
    """A compiled allocation strategy ready for execution.

    Takes a Strategy AST and prepares it for efficient evaluation,
    computing portfolio weights based on allocation rules.

    Attributes:
        strategy: The original strategy AST
        indicators: Extracted indicator specifications
        symbols: All symbols in the strategy
        min_bars: Minimum historical bars needed before evaluation
    """

    strategy: Strategy
    indicators: list[IndicatorSpec] = field(default_factory=_empty_indicator_list)
    symbols: set[str] = field(default_factory=_empty_symbol_set)
    min_bars: int = 0
    _bar_history: dict[str, list[Bar]] = field(default_factory=_empty_bar_history, repr=False)
    _indicator_cache: dict[str, NDArray[np.float64]] = field(
        default_factory=_empty_indicator_cache, repr=False
    )
    _last_allocation: dict[str, float] = field(default_factory=_empty_allocation, repr=False)

    @classmethod
    def compile(cls, strategy: Strategy) -> CompiledStrategy:
        """Compile a strategy AST into an executable form.

        Args:
            strategy: The parsed allocation strategy AST

        Returns:
            A CompiledStrategy ready for evaluation
        """
        indicators = extract_indicators(strategy)
        symbols = get_required_symbols(strategy)
        min_bars = get_max_lookback(indicators)

        # Need at least 2 bars for crossover detection
        min_bars = max(min_bars, 2)

        return cls(
            strategy=strategy,
            indicators=indicators,
            symbols=symbols,
            min_bars=min_bars,
        )

    def reset(self) -> None:
        """Reset strategy state for a new evaluation run."""
        self._bar_history = {}
        self._indicator_cache = {}
        self._last_allocation = {}

    @property
    def indicator_cache(self) -> dict[str, NDArray[np.float64]]:
        """Get the indicator cache (for inspection/debugging)."""
        return self._indicator_cache

    def add_bars(self, bars: dict[str, Bar]) -> None:
        """Add bars for all symbols.

        Args:
            bars: Dict mapping symbol to Bar
        """
        for symbol, bar in bars.items():
            if symbol not in self._bar_history:
                self._bar_history[symbol] = []
            self._bar_history[symbol].append(bar)

    def has_enough_history(self) -> bool:
        """Check if we have enough bars for evaluation."""
        if not self._bar_history:
            return False
        return all(len(bars) >= self.min_bars for bars in self._bar_history.values())

    def compute_allocation(self, bars: dict[str, Bar]) -> Allocation:
        """Compute portfolio allocation based on current market data.

        Args:
            bars: Dict mapping symbol to current Bar

        Returns:
            Allocation with weights for each symbol
        """
        # Add bars to history
        self.add_bars(bars)

        # Check if we have enough history
        if not self.has_enough_history():
            # Return empty allocation until we have enough data
            return Allocation(
                weights={},
                rebalance_needed=False,
                metadata={"reason": "insufficient_history"},
            )

        # Build evaluation state
        state = self._build_state(bars)

        # Compute allocations from strategy tree
        weights = self._evaluate_block(self.strategy, state)

        # Normalize weights to sum to 100
        weights = self._normalize_weights(weights)

        # Check if rebalance is needed
        rebalance_needed = self._check_rebalance_needed(weights)
        self._last_allocation = weights.copy()

        return Allocation(
            weights=weights,
            rebalance_needed=rebalance_needed,
            metadata={
                "strategy_name": self.strategy.name,
                "rebalance_frequency": self.strategy.rebalance or "none",
            },
        )

    def _build_state(self, current_bars: dict[str, Bar]) -> EvaluationState:
        """Build evaluation state from current data."""
        # Get previous bars
        prev_bars: dict[str, Bar] = {}
        for symbol, history in self._bar_history.items():
            if len(history) >= 2:
                prev_bars[symbol] = history[-2]

        # Compute indicators for each symbol
        indicators = self._compute_all_indicators()

        return EvaluationState(
            current_bars=current_bars,
            prev_bars=prev_bars,
            indicators=indicators,
            bar_history=self._bar_history,
        )

    def _compute_all_indicators(self) -> dict[str, float | np.ndarray]:
        """Compute all indicators from bar history."""
        all_indicators: dict[str, float | np.ndarray] = {}

        for symbol, bars in self._bar_history.items():
            if not bars:
                continue

            prices = PriceData(
                open=np.array([b.open for b in bars]),
                high=np.array([b.high for b in bars]),
                low=np.array([b.low for b in bars]),
                close=np.array([b.close for b in bars]),
                volume=np.array([b.volume for b in bars]),
            )

            # Filter indicators for this symbol
            symbol_indicators = [i for i in self.indicators if i.symbol == symbol]

            if symbol_indicators:
                computed = compute_all_indicators(symbol_indicators, prices)
                all_indicators.update(computed)

        return all_indicators

    def _evaluate_block(self, block: Block, state: EvaluationState) -> dict[str, float]:
        """Evaluate a block and return its allocation weights.

        Args:
            block: The block to evaluate
            state: Current evaluation state

        Returns:
            Dict mapping symbol to weight (0-100)
        """
        if isinstance(block, Strategy):
            # Combine children weights
            return self._evaluate_children(block.children, state)

        if isinstance(block, Group):
            # Groups just pass through to children
            return self._evaluate_children(block.children, state)

        if isinstance(block, Weight):
            return self._evaluate_weight(block, state)

        if isinstance(block, Asset):
            return self._evaluate_asset(block)

        if isinstance(block, If):
            return self._evaluate_if(block, state)

        # block is Filter (the only remaining type in the Block union)
        return self._evaluate_filter(block, state)

    def _evaluate_children(self, children: list[Block], state: EvaluationState) -> dict[str, float]:
        """Evaluate multiple children and combine their weights."""
        combined: dict[str, float] = {}

        for child in children:
            child_weights = self._evaluate_block(child, state)
            for symbol, weight in child_weights.items():
                combined[symbol] = combined.get(symbol, 0) + weight

        return combined

    def _evaluate_weight(self, weight: Weight, state: EvaluationState) -> dict[str, float]:
        """Evaluate a Weight block."""
        # First get child allocations
        child_weights: dict[str, float] = {}
        for child in weight.children:
            weights = self._evaluate_block(child, state)
            child_weights.update(weights)

        if not child_weights:
            return {}

        method = weight.method
        symbols = list(child_weights.keys())

        if method == "specified":
            # Use specified weights from assets
            return child_weights

        if method == "equal":
            # Equal weight all children
            equal_weight = 100.0 / len(symbols)
            return {s: equal_weight for s in symbols}

        if method == "momentum":
            return self._compute_momentum_weights(symbols, state, weight.lookback, weight.top)

        if method == "inverse-volatility":
            return self._compute_inverse_volatility_weights(symbols, state, weight.lookback)

        if method == "risk-parity":
            return self._compute_risk_parity_weights(symbols, state, weight.lookback)

        if method == "min-variance":
            # Simplified: use inverse volatility as approximation
            return self._compute_inverse_volatility_weights(symbols, state, weight.lookback)

        if method == "market-cap":
            # Market cap not available, fall back to equal
            return {s: 100.0 / len(symbols) for s in symbols}

        # Default to equal weight
        return {s: 100.0 / len(symbols) for s in symbols}

    def _evaluate_asset(self, asset: Asset) -> dict[str, float]:
        """Evaluate an Asset block."""
        return {asset.symbol: asset.weight or 0}

    def _evaluate_if(self, if_block: If, state: EvaluationState) -> dict[str, float]:
        """Evaluate an If block."""
        condition_met = evaluate_condition_safe(if_block.condition, state)

        if condition_met:
            return self._evaluate_block(if_block.then_block, state)
        elif if_block.else_block:
            return self._evaluate_block(if_block.else_block, state)

        return {}

    def _evaluate_filter(self, filter_block: Filter, state: EvaluationState) -> dict[str, float]:
        """Evaluate a Filter block."""
        # Get all child weights first
        child_weights: dict[str, float] = {}
        for child in filter_block.children:
            weights = self._evaluate_block(child, state)
            child_weights.update(weights)

        symbols = list(child_weights.keys())
        if not symbols:
            return {}

        # Calculate ranking criterion
        scores = self._calculate_filter_scores(
            symbols, state, filter_block.by, filter_block.lookback
        )

        # Sort by score
        sorted_symbols = sorted(symbols, key=lambda s: scores.get(s, 0), reverse=True)

        # Select top or bottom
        count = filter_block.select_count
        if filter_block.select_direction == "top":
            selected = sorted_symbols[:count]
        else:
            selected = sorted_symbols[-count:]

        # Filter weights to selected symbols
        return {s: child_weights[s] for s in selected if s in child_weights}

    def _compute_momentum_weights(
        self,
        symbols: list[str],
        state: EvaluationState,
        lookback: int | None,
        top: int | None,
    ) -> dict[str, float]:
        """Compute momentum-based weights."""
        lookback = lookback or 90
        scores: dict[str, float] = {}

        for symbol in symbols:
            if symbol in state.bar_history:
                bars = state.bar_history[symbol]
                if len(bars) >= lookback:
                    start_price = bars[-lookback].close
                    end_price = bars[-1].close
                    if start_price > 0:
                        scores[symbol] = (end_price - start_price) / start_price
                    else:
                        scores[symbol] = 0
                else:
                    scores[symbol] = 0
            else:
                scores[symbol] = 0

        # Select top performers if specified
        sorted_symbols = sorted(symbols, key=lambda s: scores.get(s, 0), reverse=True)
        if top and top < len(sorted_symbols):
            selected = sorted_symbols[:top]
        else:
            selected = sorted_symbols

        # Equal weight selected symbols
        if not selected:
            return {}
        equal_weight = 100.0 / len(selected)
        return {s: equal_weight for s in selected}

    def _compute_inverse_volatility_weights(
        self,
        symbols: list[str],
        state: EvaluationState,
        lookback: int | None,
    ) -> dict[str, float]:
        """Compute inverse volatility weights."""
        lookback = lookback or 60
        volatilities: dict[str, float] = {}

        for symbol in symbols:
            if symbol in state.bar_history:
                bars = state.bar_history[symbol]
                if len(bars) >= lookback:
                    closes = np.array([b.close for b in bars[-lookback:]])
                    returns = np.diff(closes) / closes[:-1]
                    vol = float(np.std(returns)) if len(returns) > 0 else 0.0
                    volatilities[symbol] = vol if vol > 0 else 0.0001
                else:
                    volatilities[symbol] = 0.0001
            else:
                volatilities[symbol] = 0.0001

        # Compute inverse volatility weights
        inv_vols = {s: 1.0 / v for s, v in volatilities.items()}
        total_inv_vol = sum(inv_vols.values())

        if total_inv_vol > 0:
            return {s: (v / total_inv_vol) * 100 for s, v in inv_vols.items()}

        # Fall back to equal weight
        return {s: 100.0 / len(symbols) for s in symbols}

    def _compute_risk_parity_weights(
        self,
        symbols: list[str],
        state: EvaluationState,
        lookback: int | None,
    ) -> dict[str, float]:
        """Compute risk parity weights (simplified)."""
        # Simplified: use inverse volatility as approximation
        return self._compute_inverse_volatility_weights(symbols, state, lookback)

    def _calculate_filter_scores(
        self,
        symbols: list[str],
        state: EvaluationState,
        criterion: str,
        lookback: int | None,
    ) -> dict[str, float]:
        """Calculate filter ranking scores."""
        lookback = lookback or 90
        scores: dict[str, float] = {}

        for symbol in symbols:
            if symbol not in state.bar_history:
                scores[symbol] = 0
                continue

            bars = state.bar_history[symbol]

            if criterion == "momentum":
                if len(bars) >= lookback:
                    start_price = bars[-lookback].close
                    end_price = bars[-1].close
                    scores[symbol] = (
                        (end_price - start_price) / start_price if start_price > 0 else 0
                    )
                else:
                    scores[symbol] = 0

            elif criterion == "volatility":
                if len(bars) >= lookback:
                    closes = np.array([b.close for b in bars[-lookback:]])
                    returns = np.diff(closes) / closes[:-1]
                    scores[symbol] = float(np.std(returns)) if len(returns) > 0 else 0
                else:
                    scores[symbol] = 0

            elif criterion == "volume":
                if bars:
                    scores[symbol] = float(bars[-1].volume)
                else:
                    scores[symbol] = 0

            else:
                scores[symbol] = 0

        return scores

    def _normalize_weights(self, weights: dict[str, float]) -> dict[str, float]:
        """Normalize weights to sum to 100."""
        total = sum(weights.values())
        if total <= 0:
            return weights

        return {s: (w / total) * 100 for s, w in weights.items()}

    def _check_rebalance_needed(
        self, new_weights: dict[str, float], threshold: float = 5.0
    ) -> bool:
        """Check if rebalancing is needed based on weight drift."""
        if not self._last_allocation:
            return True

        for symbol, new_weight in new_weights.items():
            old_weight = self._last_allocation.get(symbol, 0)
            if abs(new_weight - old_weight) > threshold:
                return True

        return False

    @property
    def name(self) -> str:
        """Strategy name."""
        return self.strategy.name

    @property
    def rebalance_frequency(self) -> str | None:
        """Strategy rebalance frequency."""
        return self.strategy.rebalance

    @property
    def benchmark(self) -> str | None:
        """Strategy benchmark."""
        return self.strategy.benchmark

    def __repr__(self) -> str:
        return (
            f"CompiledStrategy(name={self.name!r}, "
            f"symbols={len(self.symbols)}, "
            f"indicators={len(self.indicators)}, "
            f"min_bars={self.min_bars})"
        )


def compile_strategy(strategy: Strategy) -> CompiledStrategy:
    """Compile a strategy AST into an executable form.

    This is the main entry point for strategy compilation.

    Args:
        strategy: The parsed allocation strategy AST

    Returns:
        A CompiledStrategy ready for evaluation
    """
    return CompiledStrategy.compile(strategy)
