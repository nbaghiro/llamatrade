import { KeyRow, Panel, Side, Status, Table } from './parts';

type CheckResult = 'passed' | 'stopped' | 'skipped';

const CHECKS: readonly [string, string, CheckResult][] = [
  ['Market is open', '9:30 to 4:00', 'passed'],
  ['Order value', '≤ $5,000', 'passed'],
  ['Sleeve active, has cash', 'ledger', 'passed'],
  ['Symbol allowed', 'all', 'passed'],
  ['Position after order', '$10,414.80', 'stopped'],
  ['Daily loss', '≤ $1,000', 'skipped'],
  ['Order rate', '10 / min', 'skipped'],
];

const RESULT: Record<CheckResult, { label: string; cls: string }> = {
  passed: { label: 'Passed', cls: 'ok' },
  stopped: { label: 'Stopped', cls: 'stop' },
  skipped: { label: 'Not run', cls: 'skip' },
};

export function ChecksScreen() {
  return (
    <Panel title="Risk checks" aside={<span className="tnum">10:31:07 ET</span>} className="bare">
      <div className="order-line">
        <Side side="BUY" />
        <b className="sym">SMH</b>
        <span className="tnum">16 × $289.30</span>
        <span className="tnum t3 ml-auto">$4,628.80</span>
      </div>
      <div className="checks">
        {CHECKS.map(([name, limit, result], i) => (
          <div key={name} className={result === 'stopped' ? 'stopr' : undefined}>
            <span className="no">{i + 1}</span>
            <span className={result === 'skipped' ? 't3' : undefined}>{name}</span>
            <span className="lim">{limit}</span>
            <span className={RESULT[result].cls}>{RESULT[result].label}</span>
          </div>
        ))}
      </div>
      <div className="note-line t2">
        Not sent. The position would pass the session&apos;s $10,000 limit.
      </div>
      <div className="pn-b">
        <span className="lbl">Session limits</span>
        <KeyRow label="Order value" value="$5,000" />
        <KeyRow label="Position size" value="$10,000" />
        <KeyRow label="Daily loss" value="$1,000" />
      </div>
    </Panel>
  );
}

const ORDERS: readonly [string, 'BUY' | 'SELL', string, string, string][] = [
  ['09:31:02', 'SELL', 'XLK', '38 / 38', '301.12'],
  ['09:31:02', 'SELL', 'QQQ', '1 / 1', '619.80'],
  ['09:31:04', 'SELL', 'VTI', '30 / 30', '436.23'],
  ['09:31:05', 'BUY', 'SMH', '42 / 42', '290.85'],
  ['09:31:06', 'BUY', 'TLT', '167 / 167', '89.82'],
  ['09:31:06', 'BUY', 'GLD', '41 / 42', '243.90'],
];

export function OrdersScreen() {
  return (
    <Panel title="Order stream" aside="Nov 2 rebalance" className="bare">
      <Table
        columns={[
          { label: 'Time' },
          { label: 'Side' },
          { label: 'Symbol' },
          { label: 'Filled', numeric: true },
          { label: 'Avg', numeric: true },
        ]}
      >
        {ORDERS.map((o) => (
          <tr key={o[2]}>
            <td className="tnum t3">{o[0]}</td>
            <td>
              <Side side={o[1]} />
            </td>
            <td className="sym">{o[2]}</td>
            <td className="n">{o[3]}</td>
            <td className="n">{o[4]}</td>
          </tr>
        ))}
      </Table>
      <div className="note-line t2 ruled-top">
        Sells first, so they fund the buys. Each fill posts to its sleeve.
      </div>
      <div className="pn-b ruled-top">
        <span className="lbl">Booked to sleeves</span>
        <KeyRow label="Tech Momentum Rotation" value="3 fills" />
        <KeyRow label="Recession Radar" value="4 fills" />
      </div>
    </Panel>
  );
}

const RECON: readonly [string, number, number][] = [
  ['VTI', 28, 28],
  ['VGLT', 209, 209],
  ['IEF', 54, 54],
  ['GLD', 53, 53],
  ['DBC', 105, 105],
  ['TLT', 167, 120],
  ['QQQ', 20, 20],
  ['SMH', 42, 42],
];

export function ReconScreen() {
  return (
    <Panel
      title="Reconciliation"
      aside={<span className="tnum">Nov 13 · 10:15 ET</span>}
      className="bare"
    >
      <Table
        columns={[
          { label: 'Symbol' },
          { label: 'Ledger', numeric: true },
          { label: 'Alpaca', numeric: true },
          { label: 'Result', numeric: true },
        ]}
      >
        {RECON.map(([sym, ledger, alpaca]) => {
          const differs = ledger !== alpaca;
          return (
            <tr key={sym} className={differs ? 'sel' : undefined}>
              <td className="sym">{sym}</td>
              <td className="n">{ledger}</td>
              <td className="n">{alpaca}</td>
              <td className={`n ${differs ? 'risk' : 't2'}`}>
                {differs ? `Differs by ${ledger - alpaca}` : 'Agrees'}
              </td>
            </tr>
          );
        })}
      </Table>
      <div className="note-line ruled-top">
        <Status state="frozen" label="Recession Radar frozen until resolved" />
        <div className="t2 mt-1.5">Seven of eight agree. Nothing is adjusted for you.</div>
      </div>
    </Panel>
  );
}
