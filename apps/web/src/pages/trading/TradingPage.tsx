/**
 * Trading — read-only blotter for the tenant's live/paper sessions.
 * Wired to TradingService: sessions (summary cards), the full order blotter and
 * any open positions. Honest empty state when nothing has traded yet.
 */

import { AlertTriangle, Loader2 } from 'lucide-react';
import { useEffect } from 'react';
import { Link } from 'react-router-dom';

import { ExecutionMode } from '../../generated/proto/common_pb';
import {
  OrderSide,
  OrderStatus,
  OrderType,
  PositionSide,
  type Order,
  type Position,
  type TradingSession,
} from '../../generated/proto/trading_pb';
import { toDate, toNumber } from '../../store/backtest';
import { useTradingStore } from '../../store/trading';

function money(value: number, digits = 2): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function signedMoney(value: number, digits = 2): string {
  return `${value >= 0 ? '+' : '−'}${money(Math.abs(value), digits)}`;
}

function qty(value: number): string {
  return Number.isInteger(value) ? value.toString() : value.toFixed(2);
}

function shortDate(ts: Parameters<typeof toDate>[0]): string {
  const d = toDate(ts);
  return d
    ? d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
    : '—';
}

const ORDER_TYPE_LABEL: Record<number, string> = {
  [OrderType.MARKET]: 'Market',
  [OrderType.LIMIT]: 'Limit',
  [OrderType.STOP]: 'Stop',
  [OrderType.STOP_LIMIT]: 'Stop Limit',
  [OrderType.TRAILING_STOP]: 'Trailing',
};

const ORDER_STATUS_STYLE: Record<number, { label: string; className: string }> = {
  [OrderStatus.PENDING]: { label: 'Pending', className: 'bg-bone text-ink' },
  [OrderStatus.SUBMITTED]: { label: 'Submitted', className: 'bg-bone text-ink' },
  [OrderStatus.ACCEPTED]: { label: 'Accepted', className: 'bg-bone text-ink' },
  [OrderStatus.PARTIAL]: { label: 'Partial', className: 'bg-orange-500 text-ink' },
  [OrderStatus.FILLED]: { label: 'Filled', className: 'bg-green-600 text-bone' },
  [OrderStatus.CANCELLED]: { label: 'Cancelled', className: 'bg-gray-200 text-ink/60' },
  [OrderStatus.REJECTED]: { label: 'Rejected', className: 'bg-red-500 text-bone' },
  [OrderStatus.EXPIRED]: { label: 'Expired', className: 'bg-gray-200 text-ink/60' },
};

const th = 'px-3 py-2 border-b-2 border-ink font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-ink/55';
const td = 'px-3 py-2.5 border-b border-ink/10 font-mono text-[12px] text-ink';

function SessionCard({ session }: { session: TradingSession }) {
  const equity = toNumber(session.currentEquity);
  const start = toNumber(session.startingCapital);
  const pnl = toNumber(session.totalPnl);
  const pnlPct = start > 0 ? (pnl / start) * 100 : null;
  const winRate = session.totalTrades > 0 ? (session.winningTrades / session.totalTrades) * 100 : null;

  return (
    <div className="bg-paper border-2 border-ink shadow-[4px_4px_0_rgb(var(--lt-ink))]">
      <div className="flex items-start justify-between gap-2 px-4 py-3 border-b-2 border-ink">
        <span className="font-mono text-[12px] font-bold uppercase tracking-[0.06em] text-ink truncate">
          {session.name || 'Session'}
        </span>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span
            className={`font-mono text-[9px] font-bold uppercase tracking-wide border-[1.5px] border-ink px-1.5 py-[3px] ${
              session.mode === ExecutionMode.LIVE ? 'bg-green-600 text-bone' : 'bg-orange-500 text-ink'
            }`}
          >
            {session.mode === ExecutionMode.LIVE ? 'Live' : 'Paper'}
          </span>
          <span
            className={`font-mono text-[9px] font-bold uppercase tracking-wide border-[1.5px] border-ink px-1.5 py-[3px] ${
              session.isActive ? 'bg-ink text-bone' : 'bg-bone text-ink/60'
            }`}
          >
            {session.isActive ? 'Active' : 'Stopped'}
          </span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-3.5">
        <div>
          <div className="font-mono text-[9px] font-bold uppercase tracking-wide text-ink/45">Equity</div>
          <div className="font-mono text-[15px] font-bold mt-0.5 tabular-nums text-ink">{money(equity, 0)}</div>
        </div>
        <div>
          <div className="font-mono text-[9px] font-bold uppercase tracking-wide text-ink/45">Total P&amp;L</div>
          <div
            className={`font-mono text-[15px] font-bold mt-0.5 tabular-nums ${
              pnl >= 0 ? 'text-green-600' : 'text-red-600'
            }`}
          >
            {signedMoney(pnl, 0)}
            {pnlPct !== null && <span className="text-[11px] ml-1">({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(1)}%)</span>}
          </div>
        </div>
        <div>
          <div className="font-mono text-[9px] font-bold uppercase tracking-wide text-ink/45">Trades</div>
          <div className="font-mono text-[13px] font-bold mt-0.5 tabular-nums text-ink">{session.totalTrades}</div>
        </div>
        <div>
          <div className="font-mono text-[9px] font-bold uppercase tracking-wide text-ink/45">Win Rate</div>
          <div className="font-mono text-[13px] font-bold mt-0.5 tabular-nums text-ink">
            {winRate === null ? '—' : `${winRate.toFixed(0)}%`}
          </div>
        </div>
      </div>
    </div>
  );
}

function OrdersTable({ orders, sessionName }: { orders: Order[]; sessionName: (id: string) => string }) {
  return (
    <div className="bg-paper border-2 border-ink shadow-[4px_4px_0_rgb(var(--lt-ink))]">
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b-2 border-ink">
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.1em]">Order Blotter</span>
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-[3px]">
          {orders.length} orders
        </span>
      </div>

      {orders.length === 0 ? (
        <div className="px-4 py-8 font-mono text-[11px] uppercase tracking-[0.05em] text-ink/40 text-center">
          No orders yet
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className={`${th} text-left`}>Placed</th>
                <th className={`${th} text-left`}>Session</th>
                <th className={`${th} text-left`}>Symbol</th>
                <th className={`${th} text-left`}>Side</th>
                <th className={`${th} text-left`}>Type</th>
                <th className={`${th} text-right`}>Qty</th>
                <th className={`${th} text-right`}>Avg Fill</th>
                <th className={`${th} text-left`}>Status</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => {
                const buy = o.side === OrderSide.BUY;
                const filled = toNumber(o.filledQuantity);
                const total = toNumber(o.quantity);
                const avg = toNumber(o.averageFillPrice);
                const status = ORDER_STATUS_STYLE[o.status] ?? { label: 'Unknown', className: 'bg-bone text-ink/60' };
                return (
                  <tr key={o.id} className="last:[&>td]:border-b-0 hover:bg-bone">
                    <td className={`${td} text-left text-ink/70`}>{shortDate(o.createdAt)}</td>
                    <td className={`${td} text-left text-ink/70 truncate max-w-[160px]`}>{sessionName(o.sessionId)}</td>
                    <td className={`${td} text-left font-sans text-[13.5px] font-medium`}>{o.symbol}</td>
                    <td className={`${td} text-left`}>
                      <span
                        className={`font-mono text-[9px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-0.5 text-bone ${
                          buy ? 'bg-green-500' : 'bg-red-500'
                        }`}
                      >
                        {buy ? 'Buy' : 'Sell'}
                      </span>
                    </td>
                    <td className={`${td} text-left text-ink/70`}>{ORDER_TYPE_LABEL[o.type] ?? '—'}</td>
                    <td className={`${td} text-right tabular-nums`}>
                      {qty(filled)}
                      {total > 0 && filled !== total && <span className="text-ink/40"> / {qty(total)}</span>}
                    </td>
                    <td className={`${td} text-right tabular-nums`}>{avg > 0 ? money(avg) : '—'}</td>
                    <td className={`${td} text-left`}>
                      <span
                        className={`font-mono text-[9px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-0.5 ${status.className}`}
                      >
                        {status.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function PositionsTable({ positions, sessionName }: { positions: Position[]; sessionName: (id: string) => string }) {
  return (
    <div className="bg-paper border-2 border-ink shadow-[4px_4px_0_rgb(var(--lt-ink))]">
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b-2 border-ink">
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.1em]">Open Positions</span>
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-[3px]">
          {positions.length}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className={`${th} text-left`}>Symbol</th>
              <th className={`${th} text-left`}>Session</th>
              <th className={`${th} text-left`}>Side</th>
              <th className={`${th} text-right`}>Qty</th>
              <th className={`${th} text-right`}>Avg Entry</th>
              <th className={`${th} text-right`}>Last</th>
              <th className={`${th} text-right`}>Mkt Value</th>
              <th className={`${th} text-right`}>Unrealized P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => {
              const upnl = toNumber(p.unrealizedPnl);
              return (
                <tr key={p.id} className="last:[&>td]:border-b-0 hover:bg-bone">
                  <td className={`${td} text-left font-sans text-[13.5px] font-medium`}>{p.symbol}</td>
                  <td className={`${td} text-left text-ink/70 truncate max-w-[160px]`}>{sessionName(p.sessionId)}</td>
                  <td className={`${td} text-left text-ink/70`}>
                    {p.side === PositionSide.SHORT ? 'Short' : 'Long'}
                  </td>
                  <td className={`${td} text-right tabular-nums`}>{qty(toNumber(p.quantity))}</td>
                  <td className={`${td} text-right tabular-nums`}>{money(toNumber(p.averageEntryPrice))}</td>
                  <td className={`${td} text-right tabular-nums`}>{money(toNumber(p.currentPrice))}</td>
                  <td className={`${td} text-right tabular-nums font-bold`}>{money(toNumber(p.marketValue), 0)}</td>
                  <td className={`${td} text-right tabular-nums font-bold ${upnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {signedMoney(upnl, 0)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function TradingPage() {
  const { sessions, orders, positions, loading, loaded, error, loadBlotter } = useTradingStore();

  useEffect(() => {
    loadBlotter();
  }, [loadBlotter]);

  const sessionName = (id: string): string => sessions.find((s) => s.id === id)?.name || '—';

  const isEmpty = loaded && sessions.length === 0 && orders.length === 0;

  return (
    <div className="min-h-[calc(100vh-56px)] bg-bone bg-grid">
      <div className="max-w-[1400px] mx-auto px-6 lg:px-8 py-6 pb-16">
        <div className="flex items-end justify-between gap-3 flex-wrap mb-5">
          <div>
            <h1 className="font-display uppercase text-[42px] leading-[0.9] tracking-[0.01em]">Trading</h1>
            <div className="mt-2 font-mono text-[12px] text-ink/55">
              {loading
                ? 'Loading trading activity…'
                : `${sessions.length} ${sessions.length === 1 ? 'session' : 'sessions'} · ${orders.length} ${
                    orders.length === 1 ? 'order' : 'orders'
                  }`}
            </div>
          </div>
          <Link
            to="/portfolio"
            className="font-mono text-[10.5px] font-bold uppercase tracking-wide text-orange-500 hover:text-orange-600"
          >
            Portfolio positions →
          </Link>
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2.5 border-2 border-ink bg-red-50 px-4 py-3">
            <AlertTriangle className="w-4 h-4 text-red-600" />
            <span className="font-mono text-[13px] text-red-700">{error}</span>
          </div>
        )}

        {loading && !loaded ? (
          <div className="flex items-center justify-center gap-2 py-24 text-ink/50">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span className="font-mono text-[12px] uppercase tracking-wide">Loading blotter…</span>
          </div>
        ) : isEmpty ? (
          <div className="border-2 border-ink bg-paper shadow-[4px_4px_0_rgb(var(--lt-ink))] px-6 py-16 text-center">
            <h2 className="font-display uppercase text-2xl tracking-tight text-ink">No trading activity yet</h2>
            <p className="mt-2 font-mono text-[12px] text-ink/55 max-w-md mx-auto">
              Deploy a strategy in paper or live mode to open a trading session. Orders and fills will show up here.
            </p>
            <div className="mt-5 flex items-center justify-center gap-3">
              <Link to="/strategies" className="btn btn-primary btn-lg">
                Browse strategies
              </Link>
              <Link to="/portfolio" className="btn btn-secondary btn-lg">
                View portfolio
              </Link>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            {sessions.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {sessions.map((s) => (
                  <SessionCard key={s.id} session={s} />
                ))}
              </div>
            )}

            <OrdersTable orders={orders} sessionName={sessionName} />

            {positions.length > 0 && <PositionsTable positions={positions} sessionName={sessionName} />}
          </div>
        )}
      </div>
    </div>
  );
}
