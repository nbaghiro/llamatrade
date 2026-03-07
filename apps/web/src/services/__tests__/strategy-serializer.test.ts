import { describe, it, expect } from 'vitest';

import {
  tokenizeWithPositions,
  toKebabCase,
  fromKebabCase,
  isKebabCaseKeyword,
} from '../strategy-serializer';

describe('tokenizeWithPositions', () => {
  it('should tokenize simple S-expression', () => {
    const input = '(strategy :name "Test")';
    const tokens = tokenizeWithPositions(input);

    expect(tokens.length).toBe(5);
    expect(tokens[0]).toMatchObject({ type: 'bracket', value: '(' });
    expect(tokens[1]).toMatchObject({ type: 'keyword', value: 'strategy' });
    expect(tokens[2]).toMatchObject({ type: 'parameter', value: ':name' });
    expect(tokens[3]).toMatchObject({ type: 'string', value: '"Test"' });
    expect(tokens[4]).toMatchObject({ type: 'bracket', value: ')' });
  });

  it('should track line and column positions', () => {
    const input = '(strategy\n  :name "Test")';
    const tokens = tokenizeWithPositions(input);

    // First line
    expect(tokens[0]).toMatchObject({ line: 1, column: 1 });
    expect(tokens[1]).toMatchObject({ line: 1, column: 2 });

    // Second line
    expect(tokens[2]).toMatchObject({ line: 2, column: 3 });
    expect(tokens[3]).toMatchObject({ line: 2, column: 9 });
  });

  it('should track character offsets', () => {
    const input = '(strategy :name)';
    const tokens = tokenizeWithPositions(input);

    expect(tokens[0]).toMatchObject({ start: 0, end: 1 }); // (
    expect(tokens[1]).toMatchObject({ start: 1, end: 9 }); // strategy
    expect(tokens[2]).toMatchObject({ start: 10, end: 15 }); // :name
    expect(tokens[3]).toMatchObject({ start: 15, end: 16 }); // )
  });

  it('should classify keywords correctly', () => {
    const input = '(strategy weight group if else filter)';
    const tokens = tokenizeWithPositions(input);

    const keywords = tokens.filter((t) => t.type === 'keyword');
    expect(keywords.map((t) => t.value)).toEqual([
      'strategy', 'weight', 'group', 'if', 'else', 'filter',
    ]);
  });

  it('should classify methods correctly', () => {
    const input = '(equal momentum inverse-volatility)';
    const tokens = tokenizeWithPositions(input);

    const methods = tokens.filter((t) => t.type === 'method');
    expect(methods.map((t) => t.value)).toEqual([
      'equal', 'momentum', 'inverse-volatility',
    ]);
  });

  it('should classify indicators correctly', () => {
    const input = '(sma ema rsi macd-line bb-upper)';
    const tokens = tokenizeWithPositions(input);

    const indicators = tokens.filter((t) => t.type === 'indicator');
    expect(indicators.map((t) => t.value)).toEqual([
      'sma', 'ema', 'rsi', 'macd-line', 'bb-upper',
    ]);
  });

  it('should classify operators correctly', () => {
    const input = '(> < >= <= cross-above cross-below)';
    const tokens = tokenizeWithPositions(input);

    const operators = tokens.filter((t) => t.type === 'operator');
    expect(operators.map((t) => t.value)).toEqual([
      '>', '<', '>=', '<=', 'cross-above', 'cross-below',
    ]);
  });

  it('should classify numbers correctly', () => {
    const input = '(50 -10 0.05 100.5)';
    const tokens = tokenizeWithPositions(input);

    const numbers = tokens.filter((t) => t.type === 'number');
    expect(numbers.map((t) => t.value)).toEqual(['50', '-10', '0.05', '100.5']);
  });

  it('should classify symbols (tickers) correctly', () => {
    const input = '("SPY" VTI BND QQQ)';
    const tokens = tokenizeWithPositions(input);

    const symbols = tokens.filter((t) => t.type === 'symbol');
    expect(symbols.map((t) => t.value)).toEqual(['VTI', 'BND', 'QQQ']);
  });

  it('should handle comments', () => {
    const input = '; This is a comment\n(strategy)';
    const tokens = tokenizeWithPositions(input);

    const comments = tokens.filter((t) => t.type === 'comment');
    expect(comments.length).toBe(1);
    expect(comments[0].value).toBe('; This is a comment');
  });

  it('should handle strings with spaces', () => {
    const input = '(:name "My Strategy Name")';
    const tokens = tokenizeWithPositions(input);

    const strings = tokens.filter((t) => t.type === 'string');
    expect(strings.length).toBe(1);
    expect(strings[0].value).toBe('"My Strategy Name"');
  });

  it('should handle nested brackets', () => {
    const input = '((sma close 20) (ema close 50))';
    const tokens = tokenizeWithPositions(input);

    const brackets = tokens.filter((t) => t.type === 'bracket');
    expect(brackets.length).toBe(6); // 3 opening, 3 closing
  });

  it('should handle array syntax', () => {
    const input = '[:symbols ["SPY" "QQQ"]]';
    const tokens = tokenizeWithPositions(input);

    const brackets = tokens.filter((t) => t.type === 'bracket');
    expect(brackets.map((t) => t.value)).toContain('[');
    expect(brackets.map((t) => t.value)).toContain(']');
  });
});

describe('case conversion helpers', () => {
  describe('toKebabCase', () => {
    it('should convert snake_case to kebab-case', () => {
      expect(toKebabCase('inverse_volatility')).toBe('inverse-volatility');
      expect(toKebabCase('min_variance')).toBe('min-variance');
      expect(toKebabCase('risk_parity')).toBe('risk-parity');
    });

    it('should leave already kebab-case unchanged', () => {
      expect(toKebabCase('inverse-volatility')).toBe('inverse-volatility');
    });

    it('should leave single words unchanged', () => {
      expect(toKebabCase('equal')).toBe('equal');
      expect(toKebabCase('momentum')).toBe('momentum');
    });
  });

  describe('fromKebabCase', () => {
    it('should convert kebab-case to snake_case', () => {
      expect(fromKebabCase('inverse-volatility')).toBe('inverse_volatility');
      expect(fromKebabCase('min-variance')).toBe('min_variance');
      expect(fromKebabCase('risk-parity')).toBe('risk_parity');
    });

    it('should leave already snake_case unchanged', () => {
      expect(fromKebabCase('inverse_volatility')).toBe('inverse_volatility');
    });
  });

  describe('isKebabCaseKeyword', () => {
    it('should return true for DSL kebab-case keywords', () => {
      expect(isKebabCaseKeyword('inverse-volatility')).toBe(true);
      expect(isKebabCaseKeyword('min-variance')).toBe(true);
      expect(isKebabCaseKeyword('cross-above')).toBe(true);
      expect(isKebabCaseKeyword('macd-line')).toBe(true);
    });

    it('should return false for non-kebab keywords', () => {
      expect(isKebabCaseKeyword('equal')).toBe(false);
      expect(isKebabCaseKeyword('momentum')).toBe(false);
      expect(isKebabCaseKeyword('sma')).toBe(false);
    });
  });
});

describe('round-trip case conversion', () => {
  it('should round-trip weight methods', () => {
    const methods = ['inverse_volatility', 'min_variance', 'risk_parity'];

    for (const method of methods) {
      const kebab = toKebabCase(method);
      const snake = fromKebabCase(kebab);
      expect(snake).toBe(method);
    }
  });
});
