import { NotificationCategory } from '@llamatrade/core/proto/events_pb';
import { describe, expect, it } from 'vitest';

import { emailPreview } from '../emailPreview';
import {
  accountHealth,
  healthSummary,
  joinNames,
  monthForecast,
  problemText,
  type HealthCheck,
  type HealthSession,
} from '../health';

const paper = { isPaper: true, isActive: true, apiKeyPrefix: 'PKTX4F2Q' };
const live = { isPaper: false, isActive: true, apiKeyPrefix: 'AKLM9Z1R' };
const at = new Date('2026-11-17T15:38:00Z');
const rejected: HealthCheck = { at, valid: false, isPaper: true, message: 'unauthorized' };
const session = (name: string, kind: 'live' | 'paper', running = true, next?: string) =>
  ({ name, kind, running, nextRun: next ? new Date(next) : null }) satisfies HealthSession;

describe('accountHealth', () => {
  it('reports nothing wrong when every stored key is active', () => {
    const h = accountHealth([paper, live], null, []);
    expect(h).toEqual({ connected: ['live', 'paper'], problems: [] });
    expect(healthSummary(h)).toMatchObject({ tone: 'ok', title: 'Both accounts connected' });
  });

  it('marks paper rejected from a failed check, with the running paper sessions it holds up', () => {
    const h = accountHealth([paper, live], rejected, [
      session('Recession Radar', 'paper', true, '2026-11-19T00:00:00Z'),
      session('Momentum Sectors', 'paper', true, '2026-11-18T00:00:00Z'),
      session('Stopped one', 'paper', false),
      session('All-Weather', 'live'),
    ]);
    expect(h.problems).toHaveLength(1);
    const p = h.problems[0];
    expect(p).toMatchObject({
      kind: 'paper',
      reason: 'rejected',
      affected: ['Recession Radar', 'Momentum Sectors'],
      next: { name: 'Momentum Sectors' },
    });
    const t = problemText(p);
    expect(t.happened).toBe('Alpaca rejected the paper keys at 10:38 ET (unauthorized).');
    expect(t.affects).toBe(
      "Recession Radar and Momentum Sectors can't place orders until the keys are fixed. The next rebalance is Momentum Sectors on Nov 18."
    );
    expect(t.short).toBe('Paper keys rejected');
    expect(healthSummary(h).tone).toBe('risk');
  });

  it('ignores a failed check for the other kind of account', () => {
    expect(accountHealth([live], rejected, []).problems).toEqual([]);
  });

  it('treats switched-off keys as a problem even without a check', () => {
    const h = accountHealth([{ ...live, isActive: false }], null, []);
    expect(h.problems[0]).toMatchObject({ kind: 'live', reason: 'inactive', affected: [] });
    expect(problemText(h.problems[0])).toMatchObject({
      happened: 'The stored live keys are switched off.',
      short: 'Live keys off',
    });
    expect(problemText(h.problems[0]).affects).toContain('nothing is held up');
  });

  it('counts a kind as fine when any of its keys is active', () => {
    const h = accountHealth([{ ...paper, isActive: false }, paper], null, []);
    expect(h.problems).toEqual([]);
  });

  it('says plainly when nothing is connected, and which one is missing', () => {
    expect(healthSummary(accountHealth([], null, []))).toMatchObject({
      tone: 'none',
      title: 'No broker connected',
    });
    expect(healthSummary(accountHealth([paper], null, []))).toMatchObject({
      tone: 'ok',
      title: 'Alpaca paper connected',
    });
  });
});

describe('joinNames', () => {
  it.each([
    [[], ''],
    [['A'], 'A'],
    [['A', 'B'], 'A and B'],
    [['A', 'B', 'C'], 'A, B and C'],
    [['A', 'B', 'C', 'D', 'E'], 'A, B and 3 more'],
  ])('joins %j', (names, out) => {
    expect(joinNames(names)).toBe(out);
  });
});

describe('monthForecast', () => {
  it('projects usage so far across the month at the same pace', () => {
    expect(monthForecast(100, new Date(2026, 10, 11, 0, 0))).toBe(300);
  });

  it('never forecasts below what is already used', () => {
    expect(monthForecast(50, new Date(2026, 10, 30, 23, 59))).toBe(50);
  });

  it('says nothing on the first day or with no usage', () => {
    expect(monthForecast(10, new Date(2026, 10, 1, 12))).toBeNull();
    expect(monthForecast(0, new Date(2026, 10, 15))).toBeNull();
  });
});

describe('emailPreview', () => {
  it('mirrors the service template, with example values in the filled-in fields', () => {
    expect(emailPreview(NotificationCategory.ORDER_REJECTED)).toEqual({
      subject: 'LlamaTrade: Order rejected',
      body: 'Your order TLT was rejected: insufficient buying power',
    });
    expect(emailPreview(NotificationCategory.SLEEVE_FROZEN).body).toContain(
      'frozen: Alpaca and the ledger disagree on TLT.'
    );
    expect(emailPreview(NotificationCategory.SESSION_STOPPED).body).toBe(
      'A live trading session stopped: you stopped it'
    );
    expect(emailPreview(NotificationCategory.ORDER_FILLED).body).toBe(
      'Your order TLT ($3,797.22) filled.'
    );
  });

  it('falls back for a kind with no template', () => {
    expect(emailPreview(NotificationCategory.UNSPECIFIED).subject).toBe('LlamaTrade: Notification');
  });
});
