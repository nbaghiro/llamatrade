"""S-expression parser for allocation-based strategy DSL."""

from __future__ import annotations

import re
from typing import Literal as TypingLiteral
from typing import cast

from llamatrade_dsl.ast import (
    COMPARISON_OPS,
    CROSSOVER_OPS,
    FILTER_CRITERIA,
    INDICATORS,
    LOGICAL_OPS,
    METRICS,
    REBALANCE_FREQUENCIES,
    WEIGHT_METHODS,
    Asset,
    Block,
    Comparison,
    ComparisonOperator,
    Condition,
    Crossover,
    CrossoverDirection,
    Filter,
    FilterCriteria,
    Group,
    If,
    Indicator,
    LogicalOp,
    LogicalOperator,
    Metric,
    NumericLiteral,
    Price,
    PriceField,
    RebalanceFrequency,
    SelectDirection,
    SourceLocation,
    Strategy,
    Value,
    Weight,
    WeightMethod,
)


class ParseError(Exception):
    """Raised when parsing fails."""

    def __init__(self, message: str, position: int = 0, line: int = 1, column: int = 1):
        self.position = position
        self.line = line
        self.column = column
        super().__init__(f"{message} at line {line}, column {column}")


class Tokenizer:
    """Tokenize S-expression source into tokens."""

    TOKEN_PATTERN = re.compile(
        r"""
        (?P<LPAREN>\()|
        (?P<RPAREN>\))|
        (?P<STRING>"(?:[^"\\]|\\.)*")|
        (?P<KEYWORD>:[a-zA-Z_][a-zA-Z0-9_-]*)|
        (?P<NUMBER>-?[0-9]+\.?[0-9]*)|
        (?P<OPERATOR>>=|<=|!=|crosses-above|crosses-below|[><+\-*/=])|
        (?P<SYMBOL>[a-zA-Z_$][a-zA-Z0-9_-]*)|
        (?P<SKIP>\s+)|
        (?P<COMMENT>;[^\n]*)
        """,
        re.VERBOSE,
    )

    def __init__(self, source: str):
        self.source = source
        self.tokens: list[tuple[str, str, int, int, int]] = []
        self._tokenize()

    def _tokenize(self) -> None:
        """Convert source to token list."""
        line = 1
        line_start = 0

        for match in self.TOKEN_PATTERN.finditer(self.source):
            kind = match.lastgroup
            value = match.group()
            start = match.start()

            # Track line numbers
            newlines = value.count("\n")
            if newlines:
                line += newlines
                line_start = match.end() - len(value.rsplit("\n", 1)[-1])

            column = start - line_start + 1

            if kind is not None and kind not in ("SKIP", "COMMENT"):
                self.tokens.append((kind, value, start, line, column))


class Parser:
    """Recursive descent parser for allocation-based strategy DSL."""

    def __init__(self, source: str):
        self.source = source
        self.tokenizer = Tokenizer(source)
        self.tokens = list(self.tokenizer.tokens)
        self.pos = 0

    def _start_location(self) -> tuple[int, int, int]:
        """Capture start position for location tracking.

        Returns (start_pos, line, column) tuple.
        """
        if self.pos < len(self.tokens):
            _, _, start, line, col = self.tokens[self.pos]
            return (start, line, col)
        return (len(self.source), 1, 1)

    def _end_location(self) -> int:
        """Get end position (character offset) from the last consumed token."""
        if self.pos > 0 and self.pos <= len(self.tokens):
            _, value, start, _, _ = self.tokens[self.pos - 1]
            return start + len(value)
        return len(self.source)

    def _make_location(self, start: tuple[int, int, int]) -> SourceLocation:
        """Create SourceLocation from start tuple and current end position."""
        start_pos, line, col = start
        end_pos = self._end_location()
        return SourceLocation(line=line, column=col, start=start_pos, end=end_pos)

    def parse(self) -> Strategy:
        """Parse the source and return a Strategy."""
        if not self.tokens:
            raise ParseError("Empty input", 0)

        result = self._parse_strategy()

        if self.pos < len(self.tokens):
            _, _, _, line, col = self.tokens[self.pos]
            raise ParseError("Unexpected tokens after strategy", line=line, column=col)

        return result

    def _current(self) -> tuple[str, str, int, int, int] | None:
        """Get current token or None if at end."""
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def _expect(self, kind: str) -> str:
        """Expect a specific token kind."""
        if self.pos >= len(self.tokens):
            raise ParseError(f"Expected {kind}, got end of input", len(self.source))

        actual_kind, value, pos, line, col = self.tokens[self.pos]
        if actual_kind != kind:
            raise ParseError(f"Expected {kind}, got {actual_kind}: {value}", pos, line, col)

        self.pos += 1
        return value

    def _expect_symbol(self, expected: str) -> None:
        """Expect a specific symbol."""
        tok = self._current()
        if tok is None:
            raise ParseError(f"Expected '{expected}', got end of input", len(self.source))

        kind, value, pos, line, col = tok
        if kind != "SYMBOL" or value != expected:
            raise ParseError(f"Expected '{expected}', got {value}", pos, line, col)
        self.pos += 1

    def _expect_keyword(self, expected: str) -> None:
        """Expect a specific keyword (with colon prefix in source)."""
        tok = self._current()
        if tok is None:
            raise ParseError(f"Expected ':{expected}', got end of input", len(self.source))

        kind, value, pos, line, col = tok
        if kind != "KEYWORD" or value != f":{expected}":
            raise ParseError(f"Expected ':{expected}', got {value}", pos, line, col)
        self.pos += 1

    def _peek_keyword(self) -> str | None:
        """Peek at current token if it's a keyword, return name without colon."""
        tok = self._current()
        if tok and tok[0] == "KEYWORD":
            return tok[1][1:]  # Strip leading colon
        return None

    def _parse_strategy(self) -> Strategy:
        """Parse (strategy "name" :rebalance ... children...)."""
        start = self._start_location()
        self._expect("LPAREN")
        self._expect_symbol("strategy")

        # Parse name (required)
        name = self._parse_string()

        # Parse optional keyword arguments
        rebalance: RebalanceFrequency | None = None
        benchmark: str | None = None
        description: str | None = None

        while self._peek_keyword() in ("rebalance", "benchmark", "description"):
            kw = self._peek_keyword()
            self.pos += 1  # consume keyword

            if kw == "rebalance":
                tok = self._current()
                if tok and tok[0] == "SYMBOL" and tok[1] in REBALANCE_FREQUENCIES:
                    rebalance = cast(RebalanceFrequency, tok[1])
                    self.pos += 1
                else:
                    raise ParseError(f"Invalid rebalance frequency: {tok[1] if tok else 'EOF'}")
            elif kw == "benchmark":
                tok = self._current()
                if tok and tok[0] == "SYMBOL":
                    benchmark = tok[1]
                    self.pos += 1
                else:
                    raise ParseError("Expected symbol for benchmark")
            elif kw == "description":
                description = self._parse_string()

        # Parse child blocks
        children: list[Block] = []
        while self._current() and self._current()[0] != "RPAREN":  # type: ignore[index]
            children.append(self._parse_block())

        self._expect("RPAREN")

        return Strategy(
            name=name,
            children=children,
            rebalance=rebalance,
            benchmark=benchmark,
            description=description,
            location=self._make_location(start),
        )

    def _parse_block(self) -> Block:
        """Parse any block type."""
        tok = self._current()
        if tok is None:
            raise ParseError("Expected block, got end of input", len(self.source))

        if tok[0] != "LPAREN":
            raise ParseError(f"Expected '(', got {tok[1]}", tok[2], tok[3], tok[4])

        # Peek at the block type (symbol after lparen)
        if self.pos + 1 >= len(self.tokens):
            raise ParseError("Unexpected end of input")

        next_tok = self.tokens[self.pos + 1]
        if next_tok[0] != "SYMBOL":
            raise ParseError(f"Expected block type, got {next_tok[1]}")

        block_type = next_tok[1]

        if block_type == "group":
            return self._parse_group()
        elif block_type == "weight":
            return self._parse_weight()
        elif block_type == "asset":
            return self._parse_asset()
        elif block_type == "if":
            return self._parse_if()
        elif block_type == "filter":
            return self._parse_filter()
        else:
            raise ParseError(
                f"Unknown block type: {block_type}",
                next_tok[2],
                next_tok[3],
                next_tok[4],
            )

    def _parse_group(self) -> Group:
        """Parse (group "name" children...)."""
        start = self._start_location()
        self._expect("LPAREN")
        self._expect_symbol("group")

        name = self._parse_string()

        children: list[Block] = []
        while self._current() and self._current()[0] != "RPAREN":  # type: ignore[index]
            children.append(self._parse_block())

        self._expect("RPAREN")

        return Group(name=name, children=children, location=self._make_location(start))

    def _parse_weight(self) -> Weight:
        """Parse (weight :method <method> [:lookback N] [:top N] children...)."""
        start = self._start_location()
        self._expect("LPAREN")
        self._expect_symbol("weight")

        # Parse :method (required)
        self._expect_keyword("method")
        tok = self._current()
        if tok is None or tok[0] != "SYMBOL":
            raise ParseError("Expected weight method")
        method_str = tok[1]
        if method_str not in WEIGHT_METHODS:
            raise ParseError(f"Invalid weight method: {method_str}")
        method = cast(WeightMethod, method_str)
        self.pos += 1

        # Parse optional :lookback and :top
        lookback: int | None = None
        top: int | None = None

        while self._peek_keyword() in ("lookback", "top"):
            kw = self._peek_keyword()
            self.pos += 1

            tok = self._current()
            if tok is None or tok[0] != "NUMBER":
                raise ParseError(f"Expected number for :{kw}")
            value = int(tok[1])
            self.pos += 1

            if kw == "lookback":
                lookback = value
            elif kw == "top":
                top = value

        # Parse children
        children: list[Block] = []
        while self._current() and self._current()[0] != "RPAREN":  # type: ignore[index]
            children.append(self._parse_block())

        self._expect("RPAREN")

        return Weight(
            method=method,
            children=children,
            lookback=lookback,
            top=top,
            location=self._make_location(start),
        )

    def _parse_asset(self) -> Asset:
        """Parse (asset SYMBOL [:weight N])."""
        start = self._start_location()
        self._expect("LPAREN")
        self._expect_symbol("asset")

        # Parse symbol
        tok = self._current()
        if tok is None or tok[0] != "SYMBOL":
            raise ParseError("Expected asset symbol")
        symbol = tok[1]
        self.pos += 1

        # Parse optional :weight
        weight: float | None = None
        if self._peek_keyword() == "weight":
            self.pos += 1
            tok = self._current()
            if tok is None or tok[0] != "NUMBER":
                raise ParseError("Expected number for :weight")
            weight = float(tok[1])
            self.pos += 1

        self._expect("RPAREN")

        return Asset(symbol=symbol, weight=weight, location=self._make_location(start))

    def _parse_if(self) -> If:
        """Parse (if condition then-block [(else else-block)])."""
        start = self._start_location()
        self._expect("LPAREN")
        self._expect_symbol("if")

        condition = self._parse_condition()
        then_block = self._parse_block()

        # Check for optional else
        else_block: Block | None = None
        tok = self._current()
        if tok and tok[0] == "LPAREN":
            # Peek for 'else'
            if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1][1] == "else":
                self._expect("LPAREN")
                self._expect_symbol("else")
                else_block = self._parse_block()
                self._expect("RPAREN")

        self._expect("RPAREN")

        return If(
            condition=condition,
            then_block=then_block,
            else_block=else_block,
            location=self._make_location(start),
        )

    def _parse_filter(self) -> Filter:
        """Parse (filter :by <criteria> :select (top/bottom N) [:lookback N] children...)."""
        start = self._start_location()
        self._expect("LPAREN")
        self._expect_symbol("filter")

        # Parse :by
        self._expect_keyword("by")
        tok = self._current()
        if tok is None or tok[0] != "SYMBOL":
            raise ParseError("Expected filter criteria")
        by_str = tok[1]
        if by_str not in FILTER_CRITERIA:
            raise ParseError(f"Invalid filter criteria: {by_str}")
        by = cast(FilterCriteria, by_str)
        self.pos += 1

        # Parse :select (top/bottom N)
        self._expect_keyword("select")
        self._expect("LPAREN")

        tok = self._current()
        if tok is None or tok[0] != "SYMBOL" or tok[1] not in ("top", "bottom"):
            raise ParseError("Expected 'top' or 'bottom' in :select")
        direction = cast(SelectDirection, tok[1])
        self.pos += 1

        tok = self._current()
        if tok is None or tok[0] != "NUMBER":
            raise ParseError("Expected number in :select")
        count = int(tok[1])
        self.pos += 1

        self._expect("RPAREN")

        # Parse optional :lookback
        lookback: int | None = None
        if self._peek_keyword() == "lookback":
            self.pos += 1
            tok = self._current()
            if tok is None or tok[0] != "NUMBER":
                raise ParseError("Expected number for :lookback")
            lookback = int(tok[1])
            self.pos += 1

        # Parse children
        children: list[Block] = []
        while self._current() and self._current()[0] != "RPAREN":  # type: ignore[index]
            children.append(self._parse_block())

        self._expect("RPAREN")

        return Filter(
            by=by,
            select_direction=direction,
            select_count=count,
            children=children,
            lookback=lookback,
            location=self._make_location(start),
        )

    def _parse_condition(self) -> Condition:
        """Parse a condition expression."""
        start = self._start_location()
        self._expect("LPAREN")

        tok = self._current()
        if tok is None:
            raise ParseError("Expected condition operator")

        # Get operator
        if tok[0] == "OPERATOR":
            op = tok[1]
            self.pos += 1
        elif tok[0] == "SYMBOL":
            op = tok[1]
            self.pos += 1
        else:
            raise ParseError(f"Expected operator, got {tok[1]}")

        if op in COMPARISON_OPS:
            left = self._parse_value()
            right = self._parse_value()
            self._expect("RPAREN")
            return Comparison(
                operator=cast(ComparisonOperator, op),
                left=left,
                right=right,
                location=self._make_location(start),
            )

        elif op in CROSSOVER_OPS:
            direction: CrossoverDirection = "above" if op == "crosses-above" else "below"
            fast = self._parse_value()
            slow = self._parse_value()
            self._expect("RPAREN")
            return Crossover(
                direction=direction,
                fast=fast,
                slow=slow,
                location=self._make_location(start),
            )

        elif op in LOGICAL_OPS:
            operands: list[Condition] = []
            while self._current() and self._current()[0] != "RPAREN":  # type: ignore[index]
                operands.append(self._parse_condition())
            self._expect("RPAREN")
            return LogicalOp(
                operator=cast(LogicalOperator, op),
                operands=tuple(operands),
                location=self._make_location(start),
            )

        else:
            raise ParseError(f"Unknown condition operator: {op}")

    def _parse_value(self) -> Value:
        """Parse a value expression (literal, price, indicator, or metric)."""
        start = self._start_location()
        tok = self._current()
        if tok is None:
            raise ParseError("Expected value")

        # Numeric literal
        if tok[0] == "NUMBER":
            self.pos += 1
            return NumericLiteral(float(tok[1]), location=self._make_location(start))

        # Must be a function call
        if tok[0] != "LPAREN":
            raise ParseError(f"Expected value expression, got {tok[1]}")

        self._expect("LPAREN")

        tok = self._current()
        if tok is None or tok[0] != "SYMBOL":
            raise ParseError("Expected function name in value expression")

        fn_name = tok[1]
        self.pos += 1

        if fn_name == "price":
            return self._parse_price_rest(start)
        elif fn_name in INDICATORS:
            return self._parse_indicator_rest(fn_name, start)
        elif fn_name in METRICS:
            return self._parse_metric_rest(
                cast(TypingLiteral["drawdown", "return", "volatility"], fn_name), start
            )
        else:
            raise ParseError(f"Unknown value function: {fn_name}")

    def _parse_price_rest(self, start: tuple[int, int, int]) -> Price:
        """Parse rest of (price SYMBOL [:field])."""
        tok = self._current()
        if tok is None or tok[0] != "SYMBOL":
            raise ParseError("Expected symbol in price expression")
        symbol = tok[1]
        self.pos += 1

        field: PriceField = "close"
        if self._current() and self._current()[0] == "KEYWORD":  # type: ignore[index]
            kw = self._current()[1][1:]  # type: ignore[index]
            if kw in ("close", "open", "high", "low", "volume"):
                field = cast(PriceField, kw)
                self.pos += 1

        self._expect("RPAREN")
        return Price(symbol=symbol, field=field, location=self._make_location(start))

    def _parse_indicator_rest(self, name: str, start: tuple[int, int, int]) -> Indicator:
        """Parse rest of (indicator SYMBOL params... [:output])."""
        tok = self._current()
        if tok is None or tok[0] != "SYMBOL":
            raise ParseError(f"Expected symbol in {name} indicator")
        symbol = tok[1]
        self.pos += 1

        # Parse numeric parameters
        params: list[int | float] = []
        while self._current() and self._current()[0] == "NUMBER":  # type: ignore[index]
            tok = self._current()
            if "." in tok[1]:  # type: ignore[index]
                params.append(float(tok[1]))  # type: ignore[index]
            else:
                params.append(int(tok[1]))  # type: ignore[index]
            self.pos += 1

        # Parse optional output keyword
        output: str | None = None
        if self._current() and self._current()[0] == "KEYWORD":  # type: ignore[index]
            output = self._current()[1][1:]  # type: ignore[index]
            self.pos += 1

        self._expect("RPAREN")
        return Indicator(
            name=name,
            symbol=symbol,
            params=tuple(params),
            output=output,
            location=self._make_location(start),
        )

    def _parse_metric_rest(
        self,
        name: TypingLiteral["drawdown", "return", "volatility"],
        start: tuple[int, int, int],
    ) -> Metric:
        """Parse rest of (metric SYMBOL [period])."""
        tok = self._current()
        if tok is None or tok[0] != "SYMBOL":
            raise ParseError(f"Expected symbol in {name} metric")
        symbol = tok[1]
        self.pos += 1

        period: int | None = None
        if self._current() and self._current()[0] == "NUMBER":  # type: ignore[index]
            period = int(self._current()[1])  # type: ignore[index]
            self.pos += 1

        self._expect("RPAREN")
        return Metric(
            name=name,
            symbol=symbol,
            period=period,
            location=self._make_location(start),
        )

    def _parse_string(self) -> str:
        """Parse a string literal."""
        tok = self._current()
        if tok is None or tok[0] != "STRING":
            raise ParseError("Expected string")
        self.pos += 1
        # Unescape string
        return tok[1][1:-1].replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")


def parse(source: str) -> Strategy:
    """Parse S-expression string to Strategy AST."""
    return Parser(source).parse()


def parse_strategy(source: str) -> Strategy:
    """Parse strategy definition to Strategy object (alias for parse)."""
    return parse(source)
