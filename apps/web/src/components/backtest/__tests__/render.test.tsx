import { create } from '@bufbuild/protobuf';
import {
  BacktestRunSchema,
  BacktestStatus,
  type BacktestRun,
} from '@llamatrade/core/proto/backtest_pb';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { partialFigures, runLog } from '../../../lib/backtestView';
import { CheckLadder } from '../../sessions/CheckLadder';
import { MonthByMonth } from '../MonthByMonth';
import { RunPanel } from '../RunPanel';
import { RunFailure, RunSummary } from '../RunSections';

const ts = (iso: string) => ({ seconds: BigInt(Date.parse(iso) / 1000), nanos: 0 });

function completedRun(): BacktestRun {
  const days = Array.from({ length: 40 }, (_, i) => new Date(Date.UTC(2025, 0, 2 + i)));
  return create(BacktestRunSchema, {
    id: 'r1',
    strategyId: 's1',
    strategyVersion: 3,
    status: BacktestStatus.COMPLETED,
    createdAt: ts('2026-11-12T16:02:00Z'),
    startedAt: ts('2026-11-12T16:02:01Z'),
    completedAt: ts('2026-11-12T16:02:04Z'),
    config: {
      startDate: ts('2025-01-02T00:00:00Z'),
      endDate: ts('2025-02-10T00:00:00Z'),
      initialCapital: { value: '25000' },
      benchmarkSymbol: 'SPY',
    },
    results: {
      benchmarkSymbol: 'SPY',
      metrics: {
        totalReturn: { value: '0.12' },
        annualizedReturn: { value: '0.06' },
        benchmarkReturn: { value: '0.15' },
        sharpeRatio: { value: '0.9' },
        sortinoRatio: { value: '1.2' },
        maxDrawdown: { value: '0.08' },
        volatility: { value: '0.1' },
        totalTrades: 4,
        winningTrades: 2,
        losingTrades: 1,
      },
      equityCurve: days.map((d, i) => ({
        timestamp: ts(d.toISOString()),
        equity: { value: String(25000 + i * 50 - (i === 20 ? 900 : 0)) },
      })),
      benchmarkEquityCurve: days.map((d, i) => ({
        timestamp: ts(d.toISOString()),
        equity: { value: String(25000 + i * 60) },
      })),
      monthlyReturns: { '2025-01': 0.04, '2025-02': -0.01 },
    },
  });
}

const html = (node: JSX.Element) => renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);

describe('run panel states render', () => {
  const base = {
    progress: 0,
    currentDate: '',
    strategyName: 'Recession Radar',
    rebalance: 'monthly' as const,
  };

  it('waits with dots while running and shows partial return', () => {
    const out = html(
      <RunPanel
        {...base}
        run={create(BacktestRunSchema, { id: 'r', status: BacktestStatus.RUNNING })}
        phase="running"
        progress={62}
        currentDate="2025-01-20"
        log={runLog(
          [{ phase: 'running', percent: 62, currentDate: '2025-01-20', message: '', atMs: 2210 }],
          0
        )}
        partial={partialFigures({ totalReturn: '0.041', maxDrawdown: '0.02' })}
      />
    );
    expect(out).toContain('replaying through 2025-01-20');
    expect(out).toContain('+4.1%');
    expect(out).toContain('after the run');
    expect(out).toContain('The curve appears when the run completes.');
  });

  it('shows metrics and the chart once completed', () => {
    const out = html(
      <RunPanel
        {...base}
        run={completedRun()}
        phase="completed"
        log={[]}
        partial={partialFigures(null)}
      />
    );
    expect(out).toContain('+12.0%');
    expect(out).toContain('SPY +15.0%');
    expect(out).toContain('−8.0%');
    expect(out).not.toContain('after the run');
  });

  it('puts the failure in place of the result', () => {
    const out = html(
      <RunPanel
        {...base}
        run={create(BacktestRunSchema, { id: 'r', status: BacktestStatus.FAILED })}
        phase="failed"
        log={runLog(
          [
            {
              phase: 'failed',
              percent: 0,
              currentDate: '',
              message: 'Unsupported weighting',
              atMs: 10,
            },
          ],
          0
        )}
        partial={partialFigures(null)}
        failure={
          <RunFailure
            phase="failed"
            message="Unsupported weighting"
            strategyId="s1"
            onBack={() => undefined}
          />
        }
      />
    );
    expect(out).toContain('couldn&#x27;t finish');
    expect(out).toContain('Open in the editor');
    expect(out).toContain('bg-risk');
  });

  it('draws holding lanes and the worst fall from the trades', () => {
    const out = html(
      <RunPanel
        {...base}
        run={completedRun()}
        phase="completed"
        log={[]}
        partial={partialFigures(null)}
        trades={[
          {
            symbol: 'TLT',
            side: 'BUY',
            quantity: 10,
            entryPrice: 90,
            exitPrice: 91,
            entryTime: new Date('2025-01-03T00:00:00Z'),
            exitTime: new Date('2025-01-20T00:00:00Z'),
            pnl: 10,
            entryReason: '',
            exitReason: '',
          },
        ]}
      />
    );
    expect(out).toContain('>TLT<');
    expect(out).toContain('Holdings are rebuilt from the trade list');
    expect(out).toContain('Drawdown from peak');
    expect(out).toContain('SPY 0.');
  });

  it('keeps the dates a failed run reached', () => {
    const run = create(BacktestRunSchema, {
      id: 'r9',
      status: BacktestStatus.FAILED,
      currentDate: '2025-01-20',
      config: { startDate: ts('2025-01-02T00:00:00Z'), endDate: ts('2025-03-31T00:00:00Z') },
    });
    const out = html(
      <RunFailure
        phase="failed"
        message="rsi(XLU, 14) needs 14 bars, got 9"
        strategyId="s1"
        onBack={() => undefined}
        run={run}
      />
    );
    expect(out).toContain('The run stopped on Jan 20, 2025.');
    expect(out).toContain('Stopped Jan 20, 2025');
    expect(out).toContain('rsi(XLU, 14) needs 14 bars, got 9');
    expect(out).toContain('/backtest?rerun=r9');
    expect(out).toContain('Copy details for support');
  });

  it('writes the summary sentence against the benchmark', () => {
    const out = html(<RunSummary run={completedRun()} strategyName="Recession Radar" />);
    expect(out).toContain('points');
    expect(out).toContain('behind');
    expect(out).toContain('SPY');
  });
});

describe('month by month and the check ladder render', () => {
  it('lists a picked month', () => {
    const out = html(
      <MonthByMonth
        run={completedRun()}
        month="2025-01"
        onMonth={() => undefined}
        trades={[
          {
            symbol: 'TLT',
            side: 'BUY',
            quantity: 10,
            entryPrice: 90,
            exitPrice: 0,
            entryTime: new Date('2025-01-03T00:00:00Z'),
            exitTime: null,
            pnl: 0,
            entryReason: 'Defensive',
            exitReason: '',
          },
        ]}
      />
    );
    expect(out).toContain('Jan 3, 2025 · Defensive');
    expect(out).toContain('TLT');
  });

  it('marks only the stopping check', () => {
    const out = html(<CheckLadder stopped={[4]} />);
    expect(out.match(/Not recorded/g)).toHaveLength(6);
    expect(out.match(/>Stopped</g)).toHaveLength(1);
    expect(out).not.toContain('Passed');
  });
});
