import { describe, expect, it } from 'vitest';

import {
  compound,
  drawdown,
  exampleBacktest,
  gaussians,
  ILLUSTRATIVE_LABEL,
  illustrativeWalk,
  monthly,
  mulberry,
  shock,
  stats,
  tradingDays,
} from '../illustrative';

describe('mulberry and gaussians', () => {
  it('are deterministic per seed', () => {
    expect(gaussians(5, 4)).toEqual(gaussians(5, 4));
    expect(gaussians(5, 4)).not.toEqual(gaussians(6, 4));
    const r = mulberry(1);
    const v = r();
    expect(v).toBeGreaterThanOrEqual(0);
    expect(v).toBeLessThan(1);
  });

  it('have roughly unit variance', () => {
    const g = gaussians(42, 5000);
    const mean = g.reduce((a, b) => a + b, 0) / g.length;
    const variance = g.reduce((a, b) => a + (b - mean) ** 2, 0) / g.length;
    expect(Math.abs(mean)).toBeLessThan(0.05);
    expect(variance).toBeGreaterThan(0.9);
    expect(variance).toBeLessThan(1.1);
  });
});

describe('tradingDays', () => {
  it('skips weekends and includes both ends', () => {
    const d = tradingDays('2026-11-13', '2026-11-16');
    expect(d.map((x) => x.toISOString().slice(0, 10))).toEqual(['2026-11-13', '2026-11-16']);
  });
});

describe('compound', () => {
  it('starts and ends exactly where asked', () => {
    const s = compound(
      gaussians(3, 50).map((x) => x * 0.01),
      100,
      120
    );
    expect(s[0]).toBe(100);
    expect(s[49]).toBeCloseTo(120, 6);
  });

  it('handles short input', () => {
    expect(compound([], 1, 2)).toEqual([]);
    expect(compound([0.1], 1, 2)).toEqual([1]);
  });
});

describe('shock', () => {
  it('spreads the amount and stays in bounds', () => {
    const z = [0, 0, 0, 0];
    shock(z, 2, 4, 0.4);
    expect(z).toEqual([0, 0, 0.1, 0.1]);
  });
});

describe('drawdown and stats', () => {
  const days = tradingDays('2026-01-05', '2026-01-09');
  const s = [100, 110, 99, 105, 121];

  it('measures distance below the running peak', () => {
    const dd = drawdown(s);
    expect(dd[0]).toBe(0);
    expect(dd[2]).toBeCloseTo(-0.1);
    expect(dd[4]).toBe(0);
  });

  it('finds the max drawdown and its recovery', () => {
    const st = stats(s, days);
    expect(st.total).toBeCloseTo(0.21);
    expect(st.mdd).toBeCloseTo(-0.1);
    expect(st.mddAt).toBe(2);
    expect(st.ddPeakAt).toBe(1);
    expect(st.recoveredAt).toBe(4);
    expect(st.recoveryDays).toBe(2);
  });

  it('reports no recovery for a series that never dips', () => {
    const st = stats([1, 2, 3, 4, 5], days);
    expect(st.mdd).toBe(0);
    expect(st.recoveredAt).toBe(-1);
    expect(st.recoveryDays).toBeNull();
  });
});

describe('monthly', () => {
  it('measures each month from the previous month end', () => {
    const days = [...tradingDays('2026-01-29', '2026-02-03')];
    const s = [100, 110, 110, 121];
    expect(monthly(s, days)).toEqual([
      { y: 2026, m: 0, r: expect.closeTo(0.1) },
      { y: 2026, m: 1, r: expect.closeTo(0.1) },
    ]);
  });
});

describe('exampleBacktest', () => {
  it('is fixed, labelled and ends at the published figures', () => {
    const bt = exampleBacktest();
    expect(ILLUSTRATIVE_LABEL).toBe('Illustrative');
    expect(bt).toBe(exampleBacktest());
    expect(bt.strategy[0]).toBe(25000);
    expect(bt.strategy[bt.strategy.length - 1]).toBeCloseTo(30352.18, 2);
    expect(bt.benchmarkValues[bt.benchmarkValues.length - 1]).toBeCloseTo(31228.4, 2);
    expect(bt.strategyStats.total).toBeCloseTo(0.2141, 3);
    expect(bt.days).toHaveLength(bt.strategy.length);
    expect(bt.months).toHaveLength(24);
  });
});

describe('illustrativeWalk', () => {
  it('stays in range and is deterministic', () => {
    const w = illustrativeWalk(7);
    expect(w).toHaveLength(28);
    expect(w.every((v) => v >= 0.05 && v <= 0.95)).toBe(true);
    expect(w).toEqual(illustrativeWalk(7));
  });
});
