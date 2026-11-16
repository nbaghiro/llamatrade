import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { SleeveStatus } from '@llamatrade/core/proto/ledger_pb';
import { OrderStatus } from '@llamatrade/core/proto/trading_pb';
import { describe, expect, it } from 'vitest';

import {
  deriveSessionState,
  nextRebalanceDate,
  orderOutcome,
  RISK_CHECKS,
  sessionFigures,
  sessionSortKey,
  sessionStateView,
  stoppingChecks,
} from '../sessionState';

describe('deriveSessionState', () => {
  it('follows the execution status', () => {
    const run = (executionStatus: ExecutionStatus, isActive = true) =>
      deriveSessionState({ isActive, executionStatus });
    expect(run(ExecutionStatus.RUNNING)).toBe('running');
    expect(run(ExecutionStatus.PAUSED)).toBe('paused');
    expect(run(ExecutionStatus.STOPPED)).toBe('stopped');
    expect(run(ExecutionStatus.ERROR)).toBe('error');
    expect(run(ExecutionStatus.PENDING, false)).toBe('starting');
  });

  it('reads is_active and ended_at when the execution is unknown or still running', () => {
    expect(deriveSessionState({ isActive: true })).toBe('running');
    expect(deriveSessionState({ isActive: false, ended: true })).toBe('stopped');
    expect(deriveSessionState({ isActive: false })).toBe('paused');
    expect(deriveSessionState({ isActive: false, executionStatus: ExecutionStatus.RUNNING })).toBe(
      'paused'
    );
    expect(
      deriveSessionState({ isActive: true, ended: true, executionStatus: ExecutionStatus.RUNNING })
    ).toBe('stopped');
  });

  it('marks a frozen sleeve frozen over running and paused', () => {
    for (const executionStatus of [ExecutionStatus.RUNNING, ExecutionStatus.PAUSED]) {
      expect(
        deriveSessionState({ isActive: true, executionStatus, sleeveStatus: SleeveStatus.FROZEN })
      ).toBe('frozen');
    }
  });

  it('keeps stopped and error ahead of a frozen sleeve, and a closed sleeve stops it', () => {
    expect(
      deriveSessionState({
        isActive: false,
        ended: true,
        executionStatus: ExecutionStatus.STOPPED,
        sleeveStatus: SleeveStatus.FROZEN,
      })
    ).toBe('stopped');
    expect(
      deriveSessionState({
        isActive: true,
        executionStatus: ExecutionStatus.ERROR,
        sleeveStatus: SleeveStatus.FROZEN,
      })
    ).toBe('error');
    expect(deriveSessionState({ isActive: true, sleeveStatus: SleeveStatus.CLOSED })).toBe(
      'stopped'
    );
  });
});

describe('sessionStateView', () => {
  it('offers the actions each state allows', () => {
    expect(sessionStateView('running').actions).toEqual(['pause', 'stop']);
    expect(sessionStateView('paused').actions).toEqual(['resume', 'stop']);
    expect(sessionStateView('stopped').actions).toEqual([]);
  });

  it('raises frozen and error for attention and counts them correctly as open', () => {
    expect(sessionStateView('frozen')).toMatchObject({
      attention: true,
      open: true,
      mark: 'frozen',
    });
    expect(sessionStateView('error')).toMatchObject({ attention: true, open: false });
    expect(sessionStateView('running').attention).toBe(false);
  });

  it('sorts attention first and stopped last', () => {
    expect(sessionSortKey('frozen')).toBeLessThan(sessionSortKey('running'));
    expect(sessionSortKey('paused')).toBeLessThan(sessionSortKey('stopped'));
  });
});

describe('orders', () => {
  it('tells a risk-check stop from a broker rejection', () => {
    expect(orderOutcome(OrderStatus.REJECTED, false)).toBe('stopped');
    expect(orderOutcome(OrderStatus.REJECTED, true)).toBe('rejected');
    expect(orderOutcome(OrderStatus.FILLED, true)).toBe('filled');
    expect(orderOutcome(OrderStatus.ACCEPTED, true)).toBe('open');
    expect(orderOutcome(OrderStatus.EXPIRED, true)).toBe('closed');
  });

  it('names the stopping checks from the service messages', () => {
    expect(stoppingChecks('Position would exceed max size $10000.00')).toEqual([4]);
    expect(stoppingChecks('Market is closed (weekend). Next open: 2026-11-16 09:30 ET')).toEqual([
      0,
    ]);
    expect(stoppingChecks('Order value $500.00 exceeds sleeve free cash $12.00')).toEqual([2]);
    expect(stoppingChecks('Order value $6000.00 exceeds limit $5000.00')).toEqual([1]);
    expect(
      stoppingChecks(
        'Daily loss limit $1000.00 exceeded; Order rate limit exceeded (max 10 orders/minute)'
      )
    ).toEqual([5, 6]);
    expect(stoppingChecks('Symbol XYZ is not in allowed list')).toEqual([3]);
    expect(stoppingChecks('insufficient buying power at broker')).toEqual([2]);
    expect(stoppingChecks('')).toEqual([]);
    expect(RISK_CHECKS).toHaveLength(7);
  });
});

describe('sessionFigures', () => {
  it('derives today and total from the value, allocation and one-day return', () => {
    const f = sessionFigures({
      currentValue: 24914.42,
      allocated: 25000,
      return1d: 0.0361,
      cash: 384.82,
    });
    expect(f.equity).toBe(24914.42);
    expect(f.today).toBeCloseTo(24914.42 - 24914.42 / 1.0361, 6);
    expect(f.todayPct).toBe(0.0361);
    expect(f.total).toBeCloseTo(-85.58, 6);
    expect(f.totalPct).toBeCloseTo(-85.58 / 25000, 9);
    expect(f.cashShare).toBeCloseTo(384.82 / 24914.42, 9);
  });

  it('leaves figures empty rather than guessing', () => {
    expect(sessionFigures({ currentValue: null, allocated: 100, return1d: 0.1, cash: 5 })).toEqual({
      equity: null,
      today: null,
      todayPct: null,
      total: null,
      totalPct: null,
      cashShare: null,
    });
    const f = sessionFigures({ currentValue: 100, allocated: 0, return1d: -1, cash: null });
    expect(f).toMatchObject({ equity: 100, today: null, total: null, cashShare: null });
  });
});

describe('nextRebalanceDate', () => {
  const day = (y: number, m: number, d: number) => new Date(Date.UTC(y, m, d));
  const iso = (d: Date | null) => d?.toISOString().slice(0, 10) ?? null;

  it('is the first trading day of the next month, quarter or year', () => {
    expect(iso(nextRebalanceDate('monthly', day(2026, 10, 13)))).toBe('2026-12-01');
    expect(iso(nextRebalanceDate('Quarterly', day(2026, 10, 13)))).toBe('2027-01-04');
    expect(iso(nextRebalanceDate('quarterly', day(2026, 2, 31)))).toBe('2026-04-01');
    expect(iso(nextRebalanceDate('annually', day(2026, 0, 2)))).toBe('2027-01-04');
  });

  it('skips weekends, New Year and Labor Day', () => {
    expect(iso(nextRebalanceDate('monthly', day(2026, 1, 10)))).toBe('2026-03-02');
    expect(iso(nextRebalanceDate('monthly', day(2025, 11, 5)))).toBe('2026-01-02');
    expect(iso(nextRebalanceDate('monthly', day(2025, 7, 20)))).toBe('2025-09-02');
    expect(iso(nextRebalanceDate('monthly', day(2022, 11, 5)))).toBe('2023-01-03');
  });

  it('is next Monday for weekly, even from a Monday', () => {
    expect(iso(nextRebalanceDate('weekly', day(2026, 10, 13)))).toBe('2026-11-16');
    expect(iso(nextRebalanceDate('weekly', day(2026, 10, 16)))).toBe('2026-11-23');
    expect(iso(nextRebalanceDate('weekly', day(2025, 7, 27)))).toBe('2025-09-02');
  });

  it('has no date for daily or unknown schedules', () => {
    expect(nextRebalanceDate('daily', day(2026, 10, 13))).toBeNull();
    expect(nextRebalanceDate('', day(2026, 10, 13))).toBeNull();
    expect(nextRebalanceDate(undefined, day(2026, 10, 13))).toBeNull();
  });
});
