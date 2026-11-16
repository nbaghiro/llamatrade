import { Sparkline } from '../../components/charts';
import { formatPct } from '../../lib/format';
import { exampleBacktest, illustrativeWalk } from '../../lib/illustrative';
import type { Shade } from '../data/editorLevels';

import { AppNav, Panel, Side, Status, Table, WeightBar, type SessionState } from './parts';

const TEMPLATES: readonly [string, string, [Shade, number][]][] = [
  [
    'Classic 60/40',
    'VOO 60 · BND 40 · quarterly',
    [
      ['h1', 60],
      ['h4', 40],
    ],
  ],
  [
    'All-Weather',
    'Five funds · quarterly',
    [
      ['h1', 30],
      ['h2', 40],
      ['h3', 15],
      ['h4', 7.5],
      ['h5', 7.5],
    ],
  ],
  [
    'Core Four',
    'Four funds, equal weight',
    [
      ['h1', 25],
      ['h2', 25],
      ['h3', 25],
      ['h4', 25],
    ],
  ],
  [
    'Tech Momentum Rotation',
    'Top 2 of 3 by momentum',
    [
      ['h1', 50],
      ['h3', 50],
    ],
  ],
  ['Golden Cross', 'SPY above its 200-day EMA, else BIL', [['h1', 100]]],
  [
    'Dual Momentum',
    'Trend test, then top 3 by momentum',
    [
      ['h1', 38.2],
      ['h2', 33.5],
      ['h3', 28.3],
    ],
  ],
  [
    'Risk Parity',
    'Inverse-volatility weights',
    [
      ['h1', 34],
      ['h2', 28],
      ['h3', 22],
      ['h4', 16],
    ],
  ],
  ['Donchian Breakout', 'Channel breakout, daily', [['h2', 100]]],
  [
    'Recession Radar',
    'RSI guard with momentum',
    [
      ['hacc', 54.3],
      ['h2', 45.7],
    ],
  ],
];

export function TemplatesScreen() {
  return (
    <>
      <AppNav on="Strategies" />
      <div className="app-main">
        <div className="hd">
          <div>
            <h3>Templates</h3>
            <div className="meta">About 80 strategies, ready to backtest</div>
          </div>
          <div className="acts">
            <span className="b">All</span>
            <span className="b">Trend</span>
            <span className="b">Rotation</span>
            <span className="b">Allocation</span>
          </div>
        </div>
        <div className="cols-3">
          {TEMPLATES.map(([name, desc, weights]) => (
            <div key={name} className="pn tcard">
              <b>{name}</b>
              <p>{desc}</p>
              <WeightBar parts={weights.map(([shade, weight]) => ({ shade, weight }))} />
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

export function StrategiesScreen() {
  const s = exampleBacktest().strategyStats;
  const total = formatPct(s.total, { dp: 1, signed: true });
  const rows: [string, string, number, string, string, SessionState][] = [
    ['All-Weather Portfolio', 'Quarterly', 3, '+14.6%', '0.79', 'running'],
    ['Recession Radar', 'Monthly', 11, total, s.sharpe.toFixed(2), 'frozen'],
    ['Tech Momentum Rotation', 'Monthly', 7, '+18.9%', '0.71', 'running'],
    ['Classic 60/40', 'Quarterly', 5, '+15.5%', '0.63', 'draft'],
    ['Core Four', 'Quarterly', 13, '+12.2%', '0.81', 'draft'],
    ['Pullback Buyer', 'Daily', 17, '+8.9%', '0.22', 'draft'],
  ];
  return (
    <>
      <AppNav on="Strategies" />
      <div className="app-main">
        <div className="hd">
          <div>
            <h3>Strategies</h3>
            <div className="meta">6 strategies · 2 in paper · 1 live</div>
          </div>
          <div className="acts">
            <span className="b">Templates</span>
            <span className="b p">New strategy</span>
          </div>
        </div>
        <div className="pn">
          <Table
            columns={[
              { label: 'Strategy' },
              { label: 'Rebalance' },
              { label: 'Trend' },
              { label: 'Backtest', numeric: true },
              { label: 'Sharpe', numeric: true },
              { label: 'State' },
            ]}
          >
            {rows.map(([name, freq, seed, ret, sharpe, state]) => (
              <tr key={name} className="tall">
                <td>
                  <b className="font-semibold">{name}</b>
                </td>
                <td className="t2">{freq}</td>
                <td>
                  <Sparkline values={illustrativeWalk(seed)} />
                </td>
                <td className="n gain">{ret}</td>
                <td className="n">{sharpe}</td>
                <td>
                  <Status state={state} />
                </td>
              </tr>
            ))}
          </Table>
        </div>
        <div className="cols-3">
          {[
            ['Deployed', '$85,000'],
            ['Best backtest', total],
            ['Average Sharpe', '0.66'],
          ].map(([a, b]) => (
            <div key={a} className="pn pn-b">
              <span className="lbl">{a}</span>
              <div className="tnum stat">{b}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

const TRADES: readonly [string, string, 'BUY' | 'SELL', string, string, string, string][] = [
  ['Oct 1, 2026', 'Else', 'BUY', 'QQQ', '3', '604.12', '1,812.36'],
  ['Oct 1, 2026', 'Else', 'SELL', 'VTI', '4', '431.70', '1,726.80'],
  ['Sep 1, 2026', 'Else', 'SELL', 'IWM', '62', '236.40', '14,656.80'],
  ['Sep 1, 2026', 'Else', 'BUY', 'QQQ', '25', '588.95', '14,723.75'],
  ['Aug 3, 2026', 'If', 'SELL', 'VTI', '34', '427.15', '14,523.10'],
  ['Aug 3, 2026', 'If', 'SELL', 'IWM', '58', '229.80', '13,328.40'],
  ['Aug 3, 2026', 'If', 'BUY', 'TLT', '190', '86.92', '16,514.80'],
  ['Aug 3, 2026', 'If', 'BUY', 'GLD', '47', '234.10', '11,002.70'],
  ['Jul 1, 2026', 'Else', 'BUY', 'IWM', '2', '228.30', '456.60'],
  ['Jun 1, 2026', 'Else', 'SELL', 'QQQ', '21', '571.20', '11,995.20'],
  ['Jun 1, 2026', 'Else', 'BUY', 'IWM', '53', '224.85', '11,917.05'],
];

export function TradesScreen() {
  return (
    <>
      <AppNav on="Backtests" />
      <div className="app-main">
        <div className="hd">
          <div>
            <h3>Recession Radar · trades</h3>
            <div className="meta">58 simulated orders over 24 rebalances</div>
          </div>
          <div className="acts">
            <span className="b">Export CSV</span>
          </div>
        </div>
        <div className="pn">
          <Table
            columns={[
              { label: 'Date' },
              { label: 'Branch' },
              { label: 'Side' },
              { label: 'Symbol' },
              { label: 'Qty', numeric: true },
              { label: 'Fill', numeric: true },
              { label: 'Value', numeric: true },
            ]}
          >
            {TRADES.map((t, i) => (
              <tr key={i}>
                <td className="tnum t2">{t[0]}</td>
                <td>{t[1]}</td>
                <td>
                  <Side side={t[2]} />
                </td>
                <td className="sym">{t[3]}</td>
                <td className="n">{t[4]}</td>
                <td className="n">{t[5]}</td>
                <td className="n">{t[6]}</td>
              </tr>
            ))}
          </Table>
        </div>
      </div>
    </>
  );
}

export function BrokerScreen() {
  return (
    <>
      <AppNav on="Portfolio" />
      <div className="app-main">
        <div className="hd">
          <div>
            <h3>Broker connection</h3>
            <div className="meta">
              LlamaTrade places orders in your Alpaca account and never holds funds
            </div>
          </div>
        </div>
        <div className="cols-even">
          <Panel title="Alpaca paper" aside={<Status state="running" label="Connected" />}>
            <div className="pn-b vgrid">
              {[
                ['Account', 'ending 9cc'],
                ['Connected with', 'Alpaca sign-in'],
                ['Keys', 'encrypted at rest'],
                ['Mode', 'Paper'],
                ['Market data', 'IEX feed'],
              ].map(([a, b]) => (
                <div key={a} className="kv ruled">
                  <span className="t2">{a}</span>
                  <span className="tnum">{b}</span>
                </div>
              ))}
            </div>
          </Panel>
          <Panel title="Alpaca live" aside={<Status state="running" label="Connected" />}>
            <div className="pn-b vgrid">
              {[
                ['Account', 'ending 4f2'],
                ['Connected with', 'Alpaca sign-in'],
                ['Keys', 'encrypted at rest'],
                ['Mode', 'Live'],
                ['Sessions', '1 running'],
              ].map(([a, b]) => (
                <div key={a} className="kv ruled">
                  <span className="t2">{a}</span>
                  <span className="tnum">{b}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
        <Panel title="Notifications" aside="where alerts go">
          <Table columns={[{ label: 'Event' }, { label: 'In app' }, { label: 'Email' }]}>
            {[
              ['Sleeve frozen by reconciliation', 'On', 'On'],
              ['Order rejected by a risk check', 'On', 'On'],
              ['Session started or stopped', 'On', 'Off'],
              ['Backtest completed', 'On', 'Off'],
            ].map(([a, b, c]) => (
              <tr key={a}>
                <td>{a}</td>
                <td>{b}</td>
                <td className={c === 'Off' ? 't3' : undefined}>{c}</td>
              </tr>
            ))}
          </Table>
        </Panel>
      </div>
    </>
  );
}
