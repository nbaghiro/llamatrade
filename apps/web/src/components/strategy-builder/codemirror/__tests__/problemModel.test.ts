import { describe, expect, it } from 'vitest';

import { cleanMessage, codeProblems, namedChecks, SUPPORTED_METHOD_WORDS } from '../problemModel';

const TECH = [
  '(strategy "Tech Momentum Rotation"',
  '  :rebalance monthly',
  '  :benchmark QQQ',
  '  (filter :by momentum :select (top 2)',
  '          :lookback 90',
  '    (weight :method market-cap',
  '      (asset QQQ)',
  '      (asset XLK)',
  '      (asset SMH))))',
].join('\n');

const MC_ERROR =
  "line 6, column 13: strategy.children[0].children[0].method: market-cap weighting is not supported (requires fundamental data not available from price bars); use 'specified' or 'equal'";

describe('cleanMessage', () => {
  it('drops the location and AST path the engine prefixes', () => {
    expect(cleanMessage(MC_ERROR)).toMatch(/^Market-cap weighting is not supported/);
  });

  it('keeps a plain message and capitalises it', () => {
    expect(cleanMessage('unknown indicator: foo')).toBe('Unknown indicator: foo');
    expect(cleanMessage('')).toBe('');
  });
});

describe('codeProblems', () => {
  it('puts an unsupported weighting under its line with each supported method as a fix', () => {
    const [p] = codeProblems(TECH, [{ line: 6, column: 13, message: MC_ERROR }]);
    expect(p.line).toBe(6);
    expect(p.title).toBe('Market cap weighting can’t run');
    expect(p.body).toMatch(/fundamentals/);
    expect(p.choices.map((c) => c.label)).toEqual(SUPPORTED_METHOD_WORDS);
    expect(p.choices.map((c) => c.label)).not.toContain('market-cap');
    expect(TECH.slice(p.mark?.from, p.mark?.to)).toBe('market-cap');
    const fix = p.choices.find((c) => c.label === 'equal');
    const fixed = TECH.slice(0, fix?.from) + fix?.insert + TECH.slice(fix?.to);
    expect(fixed).toContain('(weight :method equal');
  });

  it('keeps an error without a usable line at the top', () => {
    const [p] = codeProblems(TECH, [{ line: 0, column: 0, message: 'compilation failed: boom' }]);
    expect(p.line).toBe(0);
    expect(p.title).toBe('Compilation failed: boom');
    expect(p.choices).toEqual([]);
  });

  it('treats a line past the end as having no line', () => {
    expect(codeProblems('(strategy "x")', [{ line: 40, column: 1, message: 'bad' }])[0].line).toBe(
      0
    );
  });

  it('reports the same problem once', () => {
    const errs = [
      { line: 6, column: 13, message: MC_ERROR },
      { line: 6, column: 13, message: MC_ERROR },
    ];
    expect(codeProblems(TECH, errs)).toHaveLength(1);
  });

  it('leaves a supported method alone and reports the message as is', () => {
    const code = '(strategy "x"\n  (weight :method equal (asset FOO)))';
    const [p] = codeProblems(code, [{ line: 2, column: 3, message: 'line 2: unknown symbol FOO' }]);
    expect(p.choices).toEqual([]);
    expect(p.title).toBe('Unknown symbol FOO');
  });
});

describe('namedChecks', () => {
  const ctx = { methods: ['specified', 'momentum'], symbols: ['TLT', 'GLD'], indicators: ['rsi'] };

  it('marks every check pending while the engine runs', () => {
    expect(namedChecks(null, ctx).every((c) => c.state === 'pending')).toBe(true);
  });

  it('passes every check with what it covered when there are no errors', () => {
    const checks = namedChecks([], ctx);
    expect(checks.every((c) => c.state === 'pass')).toBe(true);
    expect(checks.find((c) => c.name === 'Every weight method is supported')?.detail).toBe(
      'specified, momentum'
    );
    expect(checks.find((c) => c.name === 'Every symbol is valid')?.detail).toBe('TLT GLD');
  });

  it('fails the check an error is about', () => {
    const checks = namedChecks([{ line: 6, column: 1, message: MC_ERROR }], ctx);
    expect(checks.find((c) => c.name === 'Every weight method is supported')?.state).toBe('fail');
    expect(checks.find((c) => c.name === 'Parses')?.state).toBe('pass');
  });

  it('keeps an error that fits no check', () => {
    const checks = namedChecks([{ line: 0, column: 0, message: 'too many things' }], ctx);
    expect(checks[checks.length - 1]).toEqual({
      name: 'Other checks',
      state: 'fail',
      detail: 'Too many things',
    });
  });
});
