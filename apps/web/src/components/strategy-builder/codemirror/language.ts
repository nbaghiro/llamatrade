// S-expression language support for CodeMirror 6
// Provides syntax highlighting for the strategy DSL

import { StreamLanguage, LanguageSupport } from '@codemirror/language';

// Token classification sets (must match strategy-serializer.ts)
const DSL_KEYWORDS = new Set([
  'strategy', 'weight', 'asset', 'group', 'if', 'else', 'filter',
  'then', 'allocation', 'universe', 'close', 'open', 'high', 'low', 'volume', 'price',
]);

const DSL_METHODS = new Set([
  'specified', 'equal', 'momentum', 'inverse-volatility', 'min-variance',
  'risk-parity', 'inverse_volatility', 'min_variance', 'risk_parity',
  'top', 'bottom',
]);

const DSL_INDICATORS = new Set([
  'sma', 'ema', 'rsi', 'macd', 'macd-line', 'macd-signal',
  'bbands', 'bb-upper', 'bb-middle', 'bb-lower',
  'atr', 'adx', 'stochastic', 'cci', 'williams-r', 'obv', 'mfi', 'vwap', 'roc',
]);

const DSL_OPERATORS = new Set([
  '>', '<', '>=', '<=', '=', '!=',
  'cross-above', 'cross-below', 'crosses-above', 'crosses-below',
]);

const DSL_LOGICAL = new Set(['and', 'or', 'not']);

interface SExprState {
  depth: number;
  inString: boolean;
}

/**
 * StreamParser for S-expression DSL syntax highlighting
 */
const sExprParser = StreamLanguage.define<SExprState>({
  name: 'sexpr-dsl',

  startState(): SExprState {
    return { depth: 0, inString: false };
  },

  token(stream, state): string | null {
    // Handle strings that span multiple lines
    if (state.inString) {
      while (!stream.eol()) {
        if (stream.next() === '"') {
          state.inString = false;
          return 'string';
        }
      }
      return 'string';
    }

    // Skip whitespace
    if (stream.eatSpace()) {
      return null;
    }

    // Comments
    if (stream.match(/;.*/)) {
      return 'comment';
    }

    // String literals
    if (stream.peek() === '"') {
      stream.next();
      while (!stream.eol()) {
        if (stream.next() === '"') {
          return 'string';
        }
      }
      state.inString = true;
      return 'string';
    }

    // Brackets - opening
    if (stream.match(/[([{]/)) {
      state.depth++;
      return 'bracket';
    }

    // Brackets - closing
    if (stream.match(/[\])}]/)) {
      state.depth = Math.max(0, state.depth - 1);
      return 'bracket';
    }

    // Parameters (keywords starting with :)
    if (stream.match(/:[a-zA-Z0-9_-]+/)) {
      return 'keyword';
    }

    // Numbers (including negative and decimals)
    if (stream.match(/-?\d+(\.\d+)?/)) {
      return 'number';
    }

    // Operators
    if (stream.match(/>=|<=|!=|>|<|=/)) {
      return 'operator';
    }

    // Identifiers and keywords
    if (stream.match(/[a-zA-Z_][a-zA-Z0-9_-]*/)) {
      const word = stream.current();
      const lower = word.toLowerCase();

      if (DSL_KEYWORDS.has(lower)) {
        return 'keyword';
      }

      if (DSL_METHODS.has(lower)) {
        return 'typeName';
      }

      if (DSL_INDICATORS.has(lower)) {
        return 'variableName.special';
      }

      if (DSL_OPERATORS.has(lower) || DSL_OPERATORS.has(word)) {
        return 'operator';
      }

      if (DSL_LOGICAL.has(lower)) {
        return 'logicOperator';
      }

      // Uppercase identifiers are likely symbols (tickers)
      if (/^[A-Z][A-Z0-9]*$/.test(word)) {
        return 'atom';
      }

      return 'variableName';
    }

    // Skip unknown characters
    stream.next();
    return null;
  },

  languageData: {
    commentTokens: { line: ';' },
    closeBrackets: { brackets: ['(', '[', '{', '"'] },
  },
});

/**
 * S-expression DSL language support for CodeMirror
 */
export function sExprDSL(): LanguageSupport {
  return new LanguageSupport(sExprParser);
}

export { sExprParser };
