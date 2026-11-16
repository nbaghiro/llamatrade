import type { Order } from '@llamatrade/core/proto/trading_pb';
import { toDate, toNumber } from '@llamatrade/core/stores/backtest';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { formatNumber } from '../../lib/format';
import { ORDER_OUTCOME_LABEL } from '../../lib/sessionState';
import { Panel, SideTag } from '../backtest/parts';
import { T } from '../backtest/tableStyles';
import { Segmented } from '../ui/Tabs';

import { outcomeOf, placedAt, sideWord } from './orderLabels';

type Filter = 'all' | 'filled' | 'open' | 'stopped';

const qty = (v: number) => formatNumber(v, { dp: Number.isInteger(v) ? 0 : 2 });

/** Every order across sessions, newest first; one that was never sent is raised in amber. */
export function Blotter({
  orders,
  sessionNames,
  limit = 12,
}: {
  orders: readonly Order[];
  sessionNames: Readonly<Record<string, string>>;
  limit?: number;
}) {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<Filter>('all');
  const [showAll, setShowAll] = useState(false);
  const sorted = [...orders].sort(
    (a, b) =>
      (toDate(b.submittedAt ?? b.createdAt)?.getTime() ?? 0) -
      (toDate(a.submittedAt ?? a.createdAt)?.getTime() ?? 0)
  );
  const matches = sorted.filter((o) => {
    const out = outcomeOf(o);
    if (filter === 'filled') return out === 'filled' || out === 'partial';
    if (filter === 'open') return out === 'open';
    if (filter === 'stopped') return out === 'stopped' || out === 'rejected';
    return true;
  });
  const shown = showAll ? matches : matches.slice(0, limit);

  return (
    <Panel
      title="Order blotter"
      aside={
        <Segmented<Filter>
          label="Order state"
          value={filter}
          onChange={setFilter}
          options={[
            { key: 'all', label: 'All' },
            { key: 'filled', label: 'Filled' },
            { key: 'open', label: 'Open' },
            { key: 'stopped', label: 'Not sent' },
          ]}
        />
      }
      footer={
        matches.length > limit ? (
          <span className="flex justify-between">
            <span>
              {shown.length} of {matches.length} orders
            </span>
            <button
              type="button"
              className="text-accent hover:underline"
              onClick={() => setShowAll((v) => !v)}
            >
              {showAll ? 'Show fewer' : 'Show all'}
            </button>
          </span>
        ) : undefined
      }
    >
      {matches.length === 0 ? (
        <p className="m-0 px-3.5 py-4 text-[12.5px] text-fg-3">
          {orders.length
            ? 'No orders match this filter.'
            : 'No orders yet. They appear here from the first rebalance.'}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className={T.table}>
            <thead>
              <tr>
                <th className={T.th}>Placed, ET</th>
                <th className={T.th}>Session</th>
                <th className={T.th}>Side</th>
                <th className={T.th}>Symbol</th>
                <th className={T.thN}>Filled</th>
                <th className={T.thN}>Avg fill</th>
                <th className={T.th}>Status</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((o) => {
                const out = outcomeOf(o);
                const stopped = out === 'stopped' || out === 'rejected';
                const avg = toNumber(o.averageFillPrice);
                return (
                  <tr
                    key={o.id}
                    onClick={() => navigate(`/trading/orders/${o.id}`)}
                    className={`cursor-pointer hover:bg-sunk ${stopped ? T.rowRisk : ''}`}
                  >
                    <td className={`${T.td} num text-fg-2`}>{placedAt(o)}</td>
                    <td className={T.td}>{sessionNames[o.sessionId] ?? '·'}</td>
                    <td className={T.td}>
                      <SideTag side={sideWord(o.side)} />
                    </td>
                    <td className={`${T.td} ${T.sym}`}>{o.symbol}</td>
                    <td className={T.tdN}>
                      {qty(toNumber(o.filledQuantity))} / {qty(toNumber(o.quantity))}
                    </td>
                    <td className={T.tdN}>
                      {avg ? formatNumber(avg) : <span className="text-fg-3">·</span>}
                    </td>
                    <td className={`${T.td} ${stopped ? 'font-semibold text-risk' : ''}`}>
                      {ORDER_OUTCOME_LABEL[out]}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
