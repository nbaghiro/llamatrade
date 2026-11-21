import { create } from '@bufbuild/protobuf';
import {
  BacktestRunSchema,
  BacktestStatus,
  type BacktestRun,
} from '@llamatrade/core/proto/backtest_pb';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { runLog, type TradeInput } from '../../../lib/backtestView';
import { ResultView } from '../ResultView';
import { RunPanel } from '../RunPanel';

const ts = (iso: string) => ({ seconds: BigInt(Date.parse(iso) / 1000), nanos: 0 });
const DAY = 86_400_000;

function run(startIso: string, days: number, withVolatility = true): BacktestRun {
  const start = Date.parse(`${startIso}T00:00:00Z`);
  const dates = Array.from({ length: days }, (_, i) => new Date(start + i * DAY));
  const end = dates[dates.length - 1].toISOString();
  return create(BacktestRunSchema, {
    id: 'r1',
    strategyId: 's1',
    strategyVersion: 3,
    status: BacktestStatus.COMPLETED,
    completedAt: ts('2026-11-16T16:18:00Z'),
    config: {
      startDate: ts(`${startIso}T00:00:00Z`),
      endDate: ts(end),
      initialCapital: { value: '25000' },
      benchmarkSymbol: 'SPY',
    },
    results: {
      benchmarkSymbol: 'SPY',
      metrics: {
        totalReturn: { value: '0.2' },
        annualizedReturn: { value: '0.1' },
        benchmarkReturn: { value: '0.3' },
        sharpeRatio: { value: '0.9' },
        sortinoRatio: { value: '1.2' },
        maxDrawdown: { value: '0.05' },
        ...(withVolatility ? { volatility: { value: '0.096' } } : {}),
        winningTrades: 2,
        losingTrades: 1,
        winRate: { value: '0.6667' },
      },
      equityCurve: dates.map((d, i) => ({
        timestamp: ts(d.toISOString()),
        equity: { value: String(25000 + i * 10 - (i % 50 === 25 ? 900 : 0)) },
      })),
      benchmarkEquityCurve: dates.map((d, i) => ({
        timestamp: ts(d.toISOString()),
        equity: { value: String(25000 + i * 12 - (i % 40 === 20 ? 2500 : 0)) },
      })),
    },
  });
}

const trade = (symbol: string, from: string, to: string): TradeInput => ({
  symbol,
  side: 'BUY',
  quantity: 10,
  entryPrice: 100,
  exitPrice: 101,
  entryTime: new Date(`${from}T00:00:00Z`),
  exitTime: new Date(`${to}T00:00:00Z`),
  pnl: 10,
  entryReason: '',
  exitReason: '',
});

const html = (node: JSX.Element) => renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);

const base = {
  strategyName: 'Recession Radar',
  rebalance: 'monthly' as const,
  session: null,
  next: null,
  onNext: () => undefined,
  onOpenTrades: () => undefined,
};

describe('ResultView', () => {
  const trades = [
    trade('VTI', '2025-01-02', '2025-02-01'),
    trade('TLT', '2025-02-01', '2025-03-15'),
    trade('GLD', '2025-02-01', '2025-03-15'),
    trade('VTI', '2025-03-15', '2025-06-30'),
  ];

  it('annotates a finished run: sentence, figures, defensive move and side boxes', () => {
    const out = html(<ResultView {...base} run={run('2025-01-02', 180)} trades={trades} />);
    expect(out).toContain('in this backtest');
    expect(out).toContain('points less than SPY');
    expect(out).toContain('It moved into bonds and gold once');
    expect(out).toContain('In GLD and TLT');
    expect(out).toContain('Worst stretch');
    expect(out).toContain('Closed trades');
    expect(out).toContain('9.6%');
    expect(out).toContain('Monthly rebalance');
    expect(out).not.toContain('Indicators this run used');
  });

  it('shows a dot, not zero, when volatility was not computed', () => {
    const out = html(<ResultView {...base} run={run('2025-01-02', 180, false)} trades={null} />);
    expect(out).toContain('Not computed for this run');
    expect(out).not.toContain('>0.0%<');
  });

  it('suggests the next range and names the session', () => {
    const out = html(
      <ResultView
        {...base}
        run={run('2025-01-02', 180)}
        trades={trades}
        session={{
          strategyId: 's1',
          version: 3,
          mode: 'paper',
          active: true,
          startedAt: null,
          stoppedAt: null,
          href: '/trading/x',
        }}
        next={{
          id: 'mar-2020',
          label: 'March 2020',
          start: '2020-01-02',
          end: '2021-12-31',
          reason: '',
        }}
      />
    );
    expect(out).toContain('v3 runs on your Alpaca paper account');
    expect(out).toContain('Test on Jan 2020 to Dec 2021');
  });

  it('shades hard stretches and folds lanes on a long run from the data floor', () => {
    const out = html(<ResultView {...base} run={run('2016-01-04', 3900)} trades={trades} />);
    expect(out).toContain('During each stretch');
    expect(out).toContain('Q4 2018');
    expect(out).toContain('Back to the high after Mar 2020');
    expect(out).toContain('Earlier than 2016');
    expect(out).toContain('Hard stretch');
  });
});

describe('RunPanel while running', () => {
  it('shows the stages, the leave-page note, so-far figures and messages', () => {
    const out = html(
      <RunPanel
        run={create(BacktestRunSchema, {
          id: 'r',
          status: BacktestStatus.RUNNING,
          config: {
            startDate: ts('2025-01-02T00:00:00Z'),
            endDate: ts('2025-12-31T00:00:00Z'),
            benchmarkSymbol: 'SPY',
          },
        })}
        phase="running"
        progress={57}
        currentDate="2025-06-10"
        log={runLog([], Date.now())}
        partial={{ totalReturn: 0.05, maxDrawdown: -0.03, benchmarkReturn: 0.04 }}
        strategyName="Recession Radar"
        rebalance="monthly"
      />
    );
    expect(out).toContain('Simulating · 57% · through Jun 10, 2025');
    expect(out).toContain('You can leave this page');
    expect(out).toContain('So far, from the run');
    expect(out).toContain('Run messages');
    expect(out).toContain('How this run trades');
  });
});
