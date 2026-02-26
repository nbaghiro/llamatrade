"""S-expression parser for strategy DSL."""

from __future__ import annotations

import re

from llamatrade_dsl.ast import (
    ASTNode,
    FunctionCall,
    Keyword,
    Literal,
    LiteralValue,
    RiskConfig,
    SizingConfig,
    Strategy,
    Symbol,
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
        (?P<LBRACKET>\[)|
        (?P<RBRACKET>\])|
        (?P<LBRACE>\{)|
        (?P<RBRACE>\})|
        (?P<STRING>"(?:[^"\\]|\\.)*")|
        (?P<KEYWORD>:[a-zA-Z_][a-zA-Z0-9_-]*)|
        (?P<NUMBER>-?[0-9]+\.?[0-9]*)|
        (?P<BOOLEAN>true|false)|
        (?P<OPERATOR>>=|<=|!=|cross-above|cross-below|[><+\-*/=])|
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

            if kind not in ("SKIP", "COMMENT"):
                self.tokens.append((kind, value, start, line, column))

    def __iter__(self):
        return iter(self.tokens)

    def __len__(self):
        return len(self.tokens)


class SExprParser:
    """
    Recursive descent parser for S-expressions.

    Supports:
    - Numbers: 42, 3.14, -5
    - Strings: "hello", "with \\"escapes\\""
    - Booleans: true, false
    - Symbols: close, open, sma, my-indicator
    - Keywords: :name, :symbols, :entry
    - Function calls: (sma close 20), (and cond1 cond2)
    - Vectors: ["AAPL" "MSFT"]
    - Maps: {:key value} (for metadata)
    """

    def __init__(self, source: str):
        self.source = source
        self.tokenizer = Tokenizer(source)
        self.tokens = list(self.tokenizer)
        self.pos = 0

    def parse(self) -> ASTNode:
        """Parse the source and return a single AST node."""
        if not self.tokens:
            raise ParseError("Empty input", 0)

        result = self._parse_expr()

        if self.pos < len(self.tokens):
            _, _, _, line, col = self.tokens[self.pos]
            raise ParseError("Unexpected tokens after expression", line=line, column=col)

        return result

    def parse_strategy(self) -> Strategy:
        """Parse a (strategy ...) definition into a Strategy object."""
        node = self.parse()

        if not isinstance(node, FunctionCall) or node.name != "strategy":
            raise ParseError("Expected (strategy ...) definition", 0)

        return self._build_strategy(node)

    def _parse_expr(self) -> ASTNode:
        """Parse a single expression."""
        if self.pos >= len(self.tokens):
            raise ParseError("Unexpected end of input", len(self.source))

        kind, value, position, line, column = self.tokens[self.pos]

        if kind == "LPAREN":
            return self._parse_list()
        elif kind == "LBRACKET":
            return self._parse_vector()
        elif kind == "LBRACE":
            return self._parse_map()
        elif kind == "NUMBER":
            self.pos += 1
            if "." in value:
                return Literal(float(value))
            return Literal(int(value))
        elif kind == "STRING":
            self.pos += 1
            # Unescape string
            unescaped = value[1:-1].replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
            return Literal(unescaped)
        elif kind == "BOOLEAN":
            self.pos += 1
            return Literal(value == "true")
        elif kind == "KEYWORD":
            self.pos += 1
            return Keyword(value[1:])  # Strip leading colon
        elif kind == "SYMBOL":
            self.pos += 1
            return Symbol(value)
        else:
            raise ParseError(f"Unexpected token: {value}", position, line, column)

    def _parse_list(self) -> FunctionCall:
        """Parse (fn arg1 arg2 ...)."""
        self._expect("LPAREN")

        if self.pos >= len(self.tokens):
            raise ParseError("Unexpected end of input in list", len(self.source))

        # Empty list check
        if self.tokens[self.pos][0] == "RPAREN":
            raise ParseError(
                "Empty list not allowed - expected function name",
                self.tokens[self.pos][2],
                self.tokens[self.pos][3],
                self.tokens[self.pos][4],
            )

        # First element must be function name (symbol or operator)
        kind, value, pos, line, col = self.tokens[self.pos]
        if kind not in ("SYMBOL", "OPERATOR"):
            raise ParseError(f"Expected function name, got {value}", pos, line, col)

        self.pos += 1
        fn_name = value

        # Parse arguments until closing paren
        args: list[ASTNode] = []
        while self.pos < len(self.tokens) and self.tokens[self.pos][0] != "RPAREN":
            args.append(self._parse_expr())

        self._expect("RPAREN")

        return FunctionCall(fn_name, tuple(args))

    def _parse_vector(self) -> Literal:
        """Parse [item1 item2 ...] as a list literal."""
        self._expect("LBRACKET")

        items: list[LiteralValue] = []
        while self.pos < len(self.tokens) and self.tokens[self.pos][0] != "RBRACKET":
            node = self._parse_expr()
            if isinstance(node, Literal):
                items.append(node.value)
            elif isinstance(node, Symbol):
                items.append(node.name)
            else:
                _, _, pos, line, col = self.tokens[self.pos - 1]
                raise ParseError("Vector elements must be literals or symbols", pos, line, col)

        self._expect("RBRACKET")

        return Literal(items)

    def _parse_map(self) -> Literal:
        """Parse {:key value ...} as a dict literal."""
        self._expect("LBRACE")

        result: dict[str, LiteralValue | ASTNode] = {}
        while self.pos < len(self.tokens) and self.tokens[self.pos][0] != "RBRACE":
            # Expect keyword
            kind, value, pos, line, col = self.tokens[self.pos]
            if kind != "KEYWORD":
                raise ParseError(f"Expected keyword in map, got {value}", pos, line, col)

            key = value[1:]  # Strip colon
            self.pos += 1

            # Parse value
            if self.pos >= len(self.tokens):
                raise ParseError(f"Missing value for key :{key}", pos, line, col)

            value_node = self._parse_expr()
            if isinstance(value_node, Literal):
                result[key] = value_node.value
            elif isinstance(value_node, Symbol):
                result[key] = value_node.name
            else:
                result[key] = value_node

        self._expect("RBRACE")

        return Literal(result)

    def _expect(self, kind: str) -> str:
        """Expect a specific token kind, raise error if not found."""
        if self.pos >= len(self.tokens):
            raise ParseError(f"Expected {kind}, got end of input", len(self.source))

        actual_kind, value, pos, line, col = self.tokens[self.pos]
        if actual_kind != kind:
            raise ParseError(f"Expected {kind}, got {actual_kind}", pos, line, col)

        self.pos += 1
        return value

    def _build_strategy(self, node: FunctionCall) -> Strategy:
        """Convert parsed (strategy ...) to Strategy object."""
        # Extract keyword arguments
        kwargs: dict[str, ASTNode] = {}
        i = 0
        while i < len(node.args):
            arg = node.args[i]
            if isinstance(arg, Keyword):
                if i + 1 >= len(node.args):
                    raise ParseError(f"Missing value for keyword :{arg.name}", 0)
                kwargs[arg.name] = node.args[i + 1]
                i += 2
            else:
                i += 1

        # Helper to extract literal values
        def get_literal(key: str, default: LiteralValue | None = None) -> LiteralValue | None:
            val = kwargs.get(key)
            if val is None:
                return default
            if isinstance(val, Literal):
                return val.value
            if isinstance(val, Symbol):
                return val.name  # Convert Symbol to string
            return None

        def get_node(key: str) -> ASTNode | None:
            val = kwargs.get(key)
            if val is None:
                return None
            return val

        # Extract required fields
        name = get_literal("name")
        if not name:
            raise ParseError("Strategy requires :name", 0)

        symbols = get_literal("symbols")
        if not symbols or not isinstance(symbols, list):
            raise ParseError("Strategy requires :symbols as a list", 0)

        timeframe = get_literal("timeframe", "1D")

        entry = get_node("entry")
        if entry is None:
            raise ParseError("Strategy requires :entry condition", 0)

        exit_cond = get_node("exit")
        if exit_cond is None:
            raise ParseError("Strategy requires :exit condition", 0)

        # Optional fields
        description = get_literal("description")
        strategy_type = get_literal("type", "custom")

        # Sizing config
        position_size_val = get_literal("position-size", 10)
        sizing_type_val = get_literal("sizing-type", "percent-equity")
        sizing = SizingConfig(
            type=str(sizing_type_val) if sizing_type_val else "percent-equity",
            value=float(position_size_val) if isinstance(position_size_val, (int, float)) else 10,
        )

        # Risk config
        risk: RiskConfig = {}
        if "stop-loss-pct" in kwargs:
            risk["stop_loss_pct"] = get_literal("stop-loss-pct")
        if "take-profit-pct" in kwargs:
            risk["take_profit_pct"] = get_literal("take-profit-pct")
        if "trailing-stop-pct" in kwargs:
            risk["trailing_stop_pct"] = get_literal("trailing-stop-pct")
        if "max-positions" in kwargs:
            risk["max_positions"] = get_literal("max-positions")
        if "max-position-size-pct" in kwargs:
            risk["max_position_size_pct"] = get_literal("max-position-size-pct")

        # Handle :risk map if provided
        risk_map = get_literal("risk")
        if isinstance(risk_map, dict):
            # Convert kebab-case to snake_case
            for k, v in risk_map.items():
                snake_key = k.replace("-", "_")
                risk[snake_key] = v

        return Strategy(
            name=name,
            symbols=symbols,
            timeframe=timeframe,
            entry=entry,
            exit=exit_cond,
            description=description,
            strategy_type=strategy_type,
            sizing=sizing,
            risk=risk,
        )


def parse(source: str) -> ASTNode:
    """Parse S-expression string to AST."""
    return SExprParser(source).parse()


def parse_strategy(source: str) -> Strategy:
    """Parse strategy definition to Strategy object."""
    return SExprParser(source).parse_strategy()
