import { DrawdownBand, LineChart, MonthlyGrid } from '../../components/charts';
import { formatMoney, formatPct } from '../../lib/format';
import { exampleBacktest } from '../../lib/illustrative';
import { INDICATORS, METRICS } from '../data/illustrative';

import { AppNav, Panel } from './parts';

const LOG: readonly [string, string][] = [
  ['0.00s', 'validated v3 · 6 symbols'],
  ['0.04s', 'queued on a worker'],
  ['0.31s', 'dataset reused from cache'],
  ['0.32s', 'warm-up · 90 bars'],
  ['0.35s', 'replaying 2024-11 → 2026-10'],
  ['3.62s', '24 rebalances · 58 orders'],
  ['3.71s', 'metrics on daily returns'],
  ['3.80s', 'completed'],
];

const iso = (d: Date) => d.toISOString().slice(0, 10);
const isoMonth = (d: Date) => iso(d).slice(0, 7);
const signed = (v: number) => formatPct(v, { dp: 1, signed: true });

export function BacktestScreen() {
  const bt = exampleBacktest();
  const s = bt.strategyStats;
  const b = bt.benchmarkStats;
  const cells: { label: string; v: string; d: string; tone?: 'gain' | 'loss' }[] = [
    {
      label: 'Total return',
      v: signed(s.total),
      d: `SPY ${signed(b.total)}`,
      tone: s.total >= 0 ? 'gain' : 'loss',
    },
    {
      label: 'CAGR',
      v: signed(s.cagr),
      d: `SPY ${signed(b.cagr)}`,
      tone: s.cagr >= 0 ? 'gain' : 'loss',
    },
    { label: 'Sharpe', v: s.sharpe.toFixed(2), d: `SPY ${b.sharpe.toFixed(2)}` },
    { label: 'Sortino', v: s.sortino.toFixed(2), d: `SPY ${b.sortino.toFixed(2)}` },
    { label: 'Max drawdown', v: signed(s.mdd), d: `SPY ${signed(b.mdd)}`, tone: 'loss' },
    {
      label: 'Volatility',
      v: formatPct(s.vol, { dp: 1 }),
      d: `SPY ${formatPct(b.vol, { dp: 1 })}`,
    },
  ];
  return (
    <>
      <AppNav on="Backtests" />
      <div className="app-main">
        <div className="hd">
          <div>
            <h3>Recession Radar · version 3</h3>
            <div className="meta tnum">
              {iso(bt.days[0])} → {iso(bt.days[bt.days.length - 1])} · $25,000 · benchmark SPY
            </div>
          </div>
          <div className="acts">
            <span className="st run">
              <i />
              Completed in 3.8 s
            </span>
            <span className="b">Export</span>
            <span className="b p">Deploy</span>
          </div>
        </div>
        <div className="pn">
          <div className="prog">
            <i />
          </div>
          <div className="bt-grid">
            <div className="log bt-log">
              {LOG.map(([t, m], i) => (
                <div key={t}>
                  <span className="ts">{t}</span>
                  <span className={i === LOG.length - 1 ? 'ok' : undefined}>{m}</span>
                </div>
              ))}
            </div>
            <div className="min-w-0">
              <div className="cells">
                {cells.map((c) => (
                  <div key={c.label}>
                    <span className="lbl">{c.label}</span>
                    <div className={`v ${c.tone ?? ''}`}>{c.v}</div>
                    <div className="d">{c.d}</div>
                  </div>
                ))}
              </div>
              <div className="bt-charts">
                <div className="leg">
                  <span>
                    <i />
                    Recession Radar
                  </span>
                  <span>
                    <i className="bm" />
                    SPY
                  </span>
                </div>
                <LineChart
                  label="Recession Radar against SPY"
                  dates={bt.days}
                  height={200}
                  series={[
                    { values: bt.benchmarkValues, kind: 'bench' },
                    { values: bt.strategy, kind: 'main', area: true },
                  ]}
                  yFormat={(v) => `${(v / 1000).toFixed(0)}k`}
                  xFormat={isoMonth}
                  base={20000}
                  pad={{ l: 36 }}
                  tooltip={(i) => (
                    <>
                      <b className="block font-medium text-fg-3">{iso(bt.days[i])}</b>
                      Strategy {formatMoney(bt.strategy[i])}
                      <br />
                      SPY {formatMoney(bt.benchmarkValues[i])}
                    </>
                  )}
                />
                <div className="lbl bt-dd">Drawdown from peak</div>
                <DrawdownBand
                  dates={bt.days}
                  drawdown={bt.drawdown}
                  height={78}
                  xFormat={isoMonth}
                  pad={{ l: 36 }}
                />
              </div>
            </div>
          </div>
        </div>
        <div className="cols-2">
          <Panel title="Monthly returns, %" aside="year compounds">
            <div className="pn-b mg-host">
              <MonthlyGrid months={bt.months} />
            </div>
          </Panel>
          <Panel title="Indicators and metrics" aside="any symbol">
            <div className="pn-b">
              <div className="ind">
                {INDICATORS.map((x) => (
                  <span key={x}>{x}</span>
                ))}
                {METRICS.map((x) => (
                  <span key={x} className="m">
                    {x}
                  </span>
                ))}
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
