import { describe, expect, it } from 'vitest';

import {
  checkCounts,
  checkItems,
  countsText,
  explainIssue,
  nextProblemLine,
  withFixed,
  type CheckItem,
} from '../checkList';

const lines = new Map([
  ['w1', 5],
  ['w2', 9],
]);

const sum = {
  ruleId: 'weight.sum',
  message: 'Weight allocations sum to 95.0%, should be 100%',
  severity: 'warning' as const,
  blockId: 'w1',
};
const dup = {
  ruleId: 'structure.no-duplicates',
  message: 'Asset "QQQ" appears 2 times in this container',
  severity: 'warning' as const,
  blockId: 'w2',
};
const missing = {
  ruleId: 'weight.specified-missing',
  message: '"IEF" needs a weight allocation',
  severity: 'error' as const,
  blockId: 'w1',
};

describe('checkItems', () => {
  it('lists errors first, then warnings by line, each placed on its block’s line', () => {
    const items = checkItems([dup, sum, missing], [], lines);
    expect(items.map((i) => [i.severity, i.line])).toEqual([
      ['error', 5],
      ['warning', 5],
      ['warning', 9],
    ]);
    expect(items[0].explain).toMatch(/^Error\. /);
    expect(items[1].explain).toMatch(/^Warning\. /);
  });

  it('adds engine errors in plain words and drops duplicates', () => {
    const err = {
      line: 6,
      column: 3,
      message: 'line 6, column 3: strategy.children[0].method: bad',
    };
    const items = checkItems([sum, sum], [err], null);
    expect(items).toHaveLength(2);
    expect(items[0]).toMatchObject({ severity: 'error', line: 6, message: 'Bad' });
    expect(items[1].line).toBeNull();
  });

  it('falls back to a generic explanation for an unknown rule', () => {
    expect(explainIssue('new.rule', 'warning')).toBe('Warning. The validator flagged this rule.');
  });
});

describe('withFixed', () => {
  const at = new Date('2026-11-18T15:40:00Z');
  it('keeps a check that went away, marked fixed', () => {
    const before = checkItems([missing, sum], [], lines);
    const after = checkItems([sum], [], lines);
    const merged = withFixed(before, after, at);
    expect(merged.map((m) => [m.message, m.fixedAt])).toEqual([
      [sum.message, null],
      [missing.message, at],
    ]);
  });

  it('reopens a fixed check that comes back and keeps the first fixed time', () => {
    const first = withFixed(checkItems([missing], [], lines), [], at);
    const later = withFixed(first, [], new Date('2026-11-18T16:00:00Z'));
    expect(later[0].fixedAt).toEqual(at);
    const back = withFixed(later, checkItems([missing], [], lines), at);
    expect(back).toHaveLength(1);
    expect(back[0].fixedAt).toBeNull();
  });
});

describe('counts and navigation', () => {
  const items: CheckItem[] = withFixed(
    checkItems([missing, sum, dup], [], lines),
    checkItems([sum, dup], [], lines),
    new Date()
  );

  it('counts only open checks', () => {
    expect(checkCounts(items)).toEqual({ errors: 0, warnings: 2 });
    expect(countsText({ errors: 1, warnings: 2 })).toBe('1 error, 2 warnings');
    expect(countsText({ errors: 0, warnings: 0 })).toBe('');
  });

  it('finds the next open problem line and wraps around', () => {
    expect(nextProblemLine(items, 1)).toBe(5);
    expect(nextProblemLine(items, 5)).toBe(9);
    expect(nextProblemLine(items, 9)).toBe(5);
    expect(nextProblemLine([], 1)).toBeNull();
  });
});
