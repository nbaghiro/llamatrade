import { toDate, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { Plus } from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { PageHead, Panel } from '../../components/backtest/parts';
import { T } from '../../components/backtest/tableStyles';
import {
  Blotter,
  buildSessionRow,
  etToday,
  nextRebalanceCell,
  railFacts,
  ReadyToDeploy,
  sinceLabel,
  sortRows,
  StatusRail,
  useMarketLine,
} from '../../components/sessions';
import { PageArt } from '../../components/ui';
import { AttentionLine, type AttentionItem } from '../../components/ui/AttentionLine';
import { Money } from '../../components/ui/Num';
import { PanelError } from '../../components/ui/PanelError';
import { SkeletonRows } from '../../components/ui/Skeleton';
import { StatusMark } from '../../components/ui/StatusMark';
import { formatNumber } from '../../lib/format';

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** /trading: the sessions console. A status rail, anything that needs you, sessions, then orders. */
export default function TradingPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const wantsDeploy = params.has('deploy');
  const sessions = useTradingStore((s) => s.sessions);
  const orders = useTradingStore((s) => s.orders);
  const executions = useTradingStore((s) => s.executions);
  const sleeves = useTradingStore((s) => s.sleeves);
  const performance = useTradingStore((s) => s.performance);
  const loading = useTradingStore((s) => s.loading);
  const loaded = useTradingStore((s) => s.loaded);
  const error = useTradingStore((s) => s.error);
  const loadBlotter = useTradingStore((s) => s.loadBlotter);
  const strategies = useBacktestStore((s) => s.strategies);
  const fetchStrategies = useBacktestStore((s) => s.fetchStrategies);
  const market = useMarketLine();

  useEffect(() => {
    loadBlotter().catch(() => undefined);
    fetchStrategies().catch(() => undefined);
  }, [loadBlotter, fetchStrategies]);

  const rows = useMemo(
    () =>
      sortRows(
        sessions.map((s) =>
          buildSessionRow(s, { executions, sleeves, performance, strategies, orders })
        )
      ),
    [sessions, executions, sleeves, performance, strategies, orders]
  );
  const names = useMemo(() => Object.fromEntries(rows.map((r) => [r.session.id, r.name])), [rows]);
  const open = rows.filter((r) => r.view.open).length;
  const firstOrder = orders
    .map((o) => toDate(o.submittedAt) ?? toDate(o.createdAt))
    .filter((d): d is Date => d !== null)
    .sort((a, b) => a.getTime() - b.getTime())[0];

  const attention: AttentionItem[] = rows
    .filter((r) => r.view.attention)
    .map((r) => ({
      id: r.session.id,
      title: `${r.name} is ${r.state === 'frozen' ? 'frozen' : 'stopped by an error'}.`,
      detail:
        r.state === 'frozen'
          ? 'The ledger and Alpaca disagree about its holdings, so new orders wait until that is resolved.'
          : r.execution?.errorMessage || 'It places no new orders.',
      action: (
        <Link to={`/trading/${r.session.id}`} className="btn btn-secondary btn-sm">
          Review
        </Link>
      ),
    }));

  const empty = loaded && !error && sessions.length === 0;
  const today = etToday();
  const rail = railFacts(
    error && !sessions.length ? null : rows,
    market,
    sleeves.length > 0,
    today
  );

  return (
    <>
      <StatusRail items={rail} />
      <div className="page relative isolate grid gap-3.5">
        <PageArt shape="live" />
        <PageHead
          title="Sessions"
          meta={
            empty
              ? 'No sessions yet · paper trading only during the beta'
              : loaded && !error
                ? `${rows.length} ${rows.length === 1 ? 'session' : 'sessions'} · ${open} open · ${formatNumber(orders.length, { dp: 0 })} orders${
                    firstOrder ? ` since ${MON[firstOrder.getMonth()]} ${firstOrder.getDate()}` : ''
                  }`
                : undefined
          }
          actions={
            !empty && (
              <>
                <Link to="/portfolio" className="btn btn-secondary">
                  Portfolio positions
                </Link>
                <Link to="/trading?deploy=1" className="btn btn-primary">
                  <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                  Deploy a strategy
                </Link>
              </>
            )
          }
        />
        {empty ? (
          <ReadyToDeploy />
        ) : error && !sessions.length ? (
          <Panel>
            <PanelError
              title="Sessions couldn't be loaded"
              cause={error}
              unaffected="Running sessions keep trading on schedule."
              onRetry={() => loadBlotter()}
              retrying={loading}
            />
          </Panel>
        ) : (
          <>
            {wantsDeploy && <ReadyToDeploy />}
            <AttentionLine items={attention} />
            <Panel>
              {!loaded ? (
                <SkeletonRows rows={4} cols={6} />
              ) : (
                <div className="overflow-x-auto">
                  <table className={T.table}>
                    <thead>
                      <tr>
                        <th className={T.th}>Session</th>
                        <th className={T.th}>State</th>
                        <th className={T.th}>Next rebalance</th>
                        <th className={T.thN}>Equity</th>
                        <th className={T.thN}>Today</th>
                        <th className={T.thN}>Total P&amp;L</th>
                        <th className={T.thN}>Orders</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => {
                        const f = r.figures;
                        const dot = <span className="text-fg-3">·</span>;
                        return (
                          <tr
                            key={r.session.id}
                            onClick={() => navigate(`/trading/${r.session.id}`)}
                            className={`cursor-pointer hover:bg-sunk ${r.state === 'stopped' ? 'text-fg-3' : ''}`}
                          >
                            <td className={`${T.td} h-11`}>
                              <Link
                                to={`/trading/${r.session.id}`}
                                className={`font-semibold hover:underline ${r.state === 'stopped' ? 'text-fg-2' : 'text-fg'}`}
                                onClick={(e) => e.stopPropagation()}
                              >
                                {r.name}
                              </Link>
                              <span className={T.sub}>
                                {r.version ? `version ${r.version} · ` : ''}
                                {r.rebalance ? `${r.rebalance.toLowerCase()} · ` : ''}since{' '}
                                {sinceLabel(r.startedAt)}
                              </span>
                            </td>
                            <td className={T.td}>
                              <StatusMark state={r.view.mark} label={r.view.label} />
                            </td>
                            <td
                              className={`${T.td} num ${r.state === 'frozen' ? 'text-risk' : ''}`}
                            >
                              {nextRebalanceCell(r, today)}
                            </td>
                            <td className={T.tdN}>
                              {f.equity === null ? dot : <Money value={f.equity} />}
                            </td>
                            <td className={T.tdN}>
                              {f.today === null ? dot : <Money value={f.today} pnl />}
                            </td>
                            <td className={T.tdN}>
                              {f.total === null ? dot : <Money value={f.total} pnl />}
                            </td>
                            <td className={T.tdN}>{r.orders}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
            {loaded && <Blotter orders={orders} sessionNames={names} />}
          </>
        )}
      </div>
    </>
  );
}
