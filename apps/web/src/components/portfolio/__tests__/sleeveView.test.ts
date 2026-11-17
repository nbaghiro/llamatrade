import { ExecutionStatus } from '@llamatrade/core/stores/portfolio';
import { describe, expect, it } from 'vitest';

import { rebalanceLabel, shortDate, sinceStart, sleeveColor, sleeveRunState } from '../sleeveView';

describe('sleeveRunState', () => {
  it('reads frozen from the ledger before anything the execution reports', () => {
    expect(sleeveRunState({ frozen: true, executionStatus: ExecutionStatus.RUNNING })).toBe(
      'frozen'
    );
  });

  it('maps each execution status to its mark', () => {
    const cases: [ExecutionStatus, string][] = [
      [ExecutionStatus.RUNNING, 'running'],
      [ExecutionStatus.PAUSED, 'paused'],
      [ExecutionStatus.ERROR, 'error'],
      [ExecutionStatus.PENDING, 'waiting'],
      [ExecutionStatus.STOPPED, 'stopped'],
      [ExecutionStatus.UNSPECIFIED, 'stopped'],
    ];
    for (const [executionStatus, state] of cases) {
      expect(sleeveRunState({ frozen: false, executionStatus })).toBe(state);
    }
  });
});

describe('sleeve labels', () => {
  it('cycles sleeve colours through the five chart tones', () => {
    expect(sleeveColor(0)).toBe('rgb(var(--chart-1))');
    expect(sleeveColor(4)).toBe('rgb(var(--chart-5))');
    expect(sleeveColor(5)).toBe('rgb(var(--chart-1))');
  });

  it('describes the schedule only when it is known', () => {
    expect(rebalanceLabel('Quarterly')).toBe('Rebalances quarterly');
    expect(rebalanceLabel('')).toBe('');
  });

  it('measures gain against the capital first allocated', () => {
    expect(sinceStart({ value: 24914.42, allocatedCapital: 25000 })).toBeCloseTo(-85.58);
  });

  it('formats dates short and leaves a missing date blank', () => {
    expect(shortDate(new Date(2026, 7, 3))).toBe('Aug 3');
    expect(shortDate(null)).toBe('');
  });
});
