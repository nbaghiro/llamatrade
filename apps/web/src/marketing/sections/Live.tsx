import type { ReactNode } from 'react';

/** 04 · Live — positions table + live order stream. */

interface Position {
  sym: string;
  qty: string;
  cost: string;
  last: string;
  mkt: string;
  pl: string;
  pct: string;
  up: boolean;
}

const POSITIONS: Position[] = [
  { sym: 'QQQ', qty: '12', cost: '468.20', last: '489.55', mkt: '$5,874.60', pl: '+$256.20', pct: '+4.6%', up: true },
  { sym: 'SMH', qty: '18', cost: '241.10', last: '253.77', mkt: '$4,567.86', pl: '+$228.06', pct: '+5.3%', up: true },
  { sym: 'SOXX', qty: '9', cost: '512.30', last: '528.66', mkt: '$4,757.94', pl: '+$147.24', pct: '+3.2%', up: true },
  { sym: 'XLK', qty: '22', cost: '229.55', last: '224.10', mkt: '$4,930.20', pl: '-$119.90', pct: '-2.4%', up: false },
  { sym: 'TLT', qty: '40', cost: '94.10', last: '91.35', mkt: '$3,654.00', pl: '-$110.00', pct: '-2.9%', up: false },
];

interface OrderRow {
  time: string;
  badge: 'filled' | 'part' | 'new';
  badgeLabel: string;
  detail: ReactNode;
  kind: string;
  kindGreen?: boolean;
}

const ORDERS: OrderRow[] = [
  { time: '09:31:04', badge: 'filled', badgeLabel: 'Filled', detail: <>BUY 12 <b>QQQ</b> @ 468.20</>, kind: 'market', kindGreen: true },
  { time: '09:31:04', badge: 'filled', badgeLabel: 'Filled', detail: <>BUY 18 <b>SMH</b> @ 241.10</>, kind: 'market', kindGreen: true },
  {
    time: '10:02:47',
    badge: 'part',
    badgeLabel: 'Partial',
    detail: (
      <>
        SELL 4/9 <b>SOXX</b> @ 528.66 <span className="g">· trim</span>
      </>
    ),
    kind: 'limit',
  },
  { time: '10:18:11', badge: 'new', badgeLabel: 'New', detail: <>STOP 22 <b>XLK</b> @ 219.00 · exit</>, kind: 'stop' },
  { time: '10:41:22', badge: 'new', badgeLabel: 'New', detail: <>STOP-LIMIT 40 <b>TLT</b> @ 90.00 / 89.60 · exit</>, kind: 'stop-limit' },
];

export function Live() {
  return (
    <section id="live">
      <div className="wrap">
        <div className="sec-head reveal">
          <span className="sec-idx">04 / LIVE</span>
          <h2 className="sec-title">
            Go live.
            <br />
            Watch it fill.
          </h2>
          <span className="sec-lead">Real-time · Every order type</span>
        </div>

        <div className="live-lead">
          <p className="stmt reveal">
            The exact strategy you backtest is the strategy that trades.{' '}
            <span className="o">No drift. No surprises.</span>
          </p>
          <p className="reveal" data-d="1">
            Rehearse risk-free in paper, then go live with real money — either way, watch orders
            fill and positions and P&amp;L update in real time: market, limit, stop and stop-limit.
            Fills from the broker are the source of truth for your position state, reconciled every
            tick.
          </p>
        </div>

        <div className="tbl-scroll reveal">
          <table className="pos" aria-label="Live positions">
            <thead>
              <tr>
                <th scope="col">Symbol</th>
                <th scope="col">Side</th>
                <th scope="col">Qty</th>
                <th scope="col">Avg cost</th>
                <th scope="col">Last</th>
                <th scope="col">Mkt value</th>
                <th scope="col">Unreal. P&amp;L</th>
                <th scope="col">%</th>
              </tr>
            </thead>
            <tbody>
              {POSITIONS.map((pos) => (
                <tr key={pos.sym}>
                  <td className="sym">{pos.sym}</td>
                  <td>
                    <span className="side-long">LONG</span>
                  </td>
                  <td>{pos.qty}</td>
                  <td>{pos.cost}</td>
                  <td>{pos.last}</td>
                  <td>{pos.mkt}</td>
                  <td className={pos.up ? 'pl-pos' : 'pl-neg'}>{pos.pl}</td>
                  <td className={pos.up ? 'pl-pos' : 'pl-neg'}>{pos.pct}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="tbl-foot reveal" data-d="1">
          <div className="cell">
            <div className="l">Account equity</div>
            <div className="v">$103,918</div>
          </div>
          <div className="cell">
            <div className="l">Day P&amp;L</div>
            <div className="v pos">+$776.40</div>
          </div>
          <div className="cell">
            <div className="l">Open positions</div>
            <div className="v acc">5</div>
          </div>
          <div className="cell">
            <div className="l">Buying power</div>
            <div className="v">$80,133</div>
          </div>
        </div>

        <div className="order-feed reveal">
          <div className="of-bar">
            <span>◉ ORDER STREAM · LIVE</span>
            <span>trade_updates</span>
          </div>
          {ORDERS.map((o, i) => (
            <div className="of-row" key={i}>
              <span className="t">{o.time}</span>
              <span className={`badge ${o.badge}`}>{o.badgeLabel}</span>
              <span>{o.detail}</span>
              <span className="grow" />
              <span className={o.kindGreen ? 'g' : undefined}>{o.kind}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
