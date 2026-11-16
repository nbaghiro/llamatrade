import { AppNav, Figure, Panel, Side, Table } from './parts';

const SESSION_ORDERS: readonly [string, 'BUY' | 'SELL', string, string, string][] = [
  ['09:31:02', 'SELL', 'XLK', '38 / 38', '301.12'],
  ['09:31:02', 'SELL', 'QQQ', '1 / 1', '619.80'],
  ['09:31:05', 'BUY', 'SMH', '42 / 42', '290.85'],
];

const CHECKS: readonly [string, string][] = [
  ['Market is open', '9:30 to 4:00'],
  ['Order value', '≤ $15,000'],
  ['Sleeve active, has cash', 'ledger'],
  ['Symbol allowed', 'all'],
  ['Position after order', '≤ $15,000'],
  ['Daily loss', '≤ $1,000'],
  ['Order rate', '10 / min'],
];

export function SessionScreen() {
  return (
    <>
      <AppNav on="Sessions" live />
      <div className="rail">
        <div>
          <span className="k">Market</span>
          <span className="v">Open 10:42:18 ET</span>
        </div>
        <div>
          <span className="k">Data</span>
          <span className="v">IEX · bar 10:42</span>
        </div>
        <div>
          <span className="k">Rebalance gate</span>
          <span className="v">Closed · opens Dec 1</span>
        </div>
        <div>
          <span className="k">Reconciliation</span>
          <span className="v">Passed 10:15</span>
        </div>
        <div>
          <span className="mode live">Live</span>
        </div>
      </div>
      <div className="app-main">
        <div className="hd">
          <div>
            <h3>Tech Momentum Rotation</h3>
            <div className="meta">Version 2 · monthly · running since Oct 1</div>
          </div>
          <div className="acts">
            <span className="st run">
              <i />
              Running
            </span>
            <span className="b">Pause</span>
            <span className="b">Stop session</span>
          </div>
        </div>
        <div className="kp pn">
          <Figure label="Sleeve equity" value="$24,914.42" detail="allocated $25,000" />
          <Figure label="Today" value="+$867.12" detail="+3.61%" tone="gain" />
          <Figure label="Total P&L" value="−$85.58" detail="−0.34%" tone="loss" />
          <Figure label="Cash" value="$384.82" detail="1.5% of sleeve" />
        </div>
        <div className="cols-session">
          <div className="vgrid">
            <Panel title="Positions" aside="ledger quantities, IEX marks">
              <Table
                columns={[
                  { label: 'Symbol' },
                  { label: 'Qty', numeric: true },
                  { label: 'Avg cost', numeric: true },
                  { label: 'Last', numeric: true },
                  { label: 'Today', numeric: true },
                  { label: 'Market value', numeric: true },
                ]}
              >
                <tr>
                  <td className="sym">QQQ</td>
                  <td className="n">20</td>
                  <td className="n">621.30</td>
                  <td className="n">618.95</td>
                  <td className="n gain">+2.89%</td>
                  <td className="n">12,379.00</td>
                </tr>
                <tr>
                  <td className="sym">SMH</td>
                  <td className="n">42</td>
                  <td className="n">290.85</td>
                  <td className="n">289.30</td>
                  <td className="n gain">+4.46%</td>
                  <td className="n">12,150.60</td>
                </tr>
                <tr>
                  <td className="t3">Cash</td>
                  <td />
                  <td />
                  <td />
                  <td />
                  <td className="n">384.82</td>
                </tr>
              </Table>
            </Panel>
            <Panel title="Orders" aside="last rebalance, Nov 2">
              <Table
                columns={[
                  { label: 'Time' },
                  { label: 'Side' },
                  { label: 'Symbol' },
                  { label: 'Filled', numeric: true },
                  { label: 'Avg', numeric: true },
                  { label: 'Status' },
                ]}
              >
                {SESSION_ORDERS.map((o) => (
                  <tr key={o[2]}>
                    <td className="tnum t3">{o[0]}</td>
                    <td>
                      <Side side={o[1]} />
                    </td>
                    <td className="sym">{o[2]}</td>
                    <td className="n">{o[3]}</td>
                    <td className="n">{o[4]}</td>
                    <td>Filled</td>
                  </tr>
                ))}
              </Table>
            </Panel>
          </div>
          <Panel title="Risk checks · BUY 42 SMH" aside="7 of 7">
            <div className="checks">
              {CHECKS.map(([a, b], i) => (
                <div key={a}>
                  <span className="no">{i + 1}</span>
                  <span>{a}</span>
                  <span className="lim">{b}</span>
                  <span className="ok">Passed</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
