import { useActivityStore, type ActivityRow } from '@llamatrade/core/stores/activity';
import { ChevronLeft, Download, Receipt } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  EmptyState,
  LoadingLabel,
  NoMatch,
  Num,
  PanelError,
  Segmented,
  SkeletonRows,
} from '../../components/ui';
import {
  ACTIVITY_FILTERS,
  activityCsv,
  causeSentence,
  groupByMonth,
  statementFlow,
  type ActivityFilter,
  type FlowKind,
} from '../../lib/portfolioView';

const TYPE_LABEL: Record<ActivityRow['group'], string> = {
  funding: 'Funding',
  allocations: 'Allocations',
  trades: 'Trades',
  income: 'Income',
};

const WHEN = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

function when(d: Date): string {
  return WHEN.format(d).replace(',', ' ·');
}

function typeOfKind(kind: FlowKind): string {
  if (kind === 'deposit' || kind === 'withdrawal') return TYPE_LABEL.funding;
  if (kind === 'allocation' || kind === 'release') return TYPE_LABEL.allocations;
  if (kind === 'dividend' || kind === 'interest') return TYPE_LABEL.income;
  return TYPE_LABEL.trades;
}

function download(csv: string) {
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `llamatrade-paper-activity-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

const TH = 'border-b border-line px-3.5 py-2 text-left font-mono text-[11px] font-medium text-fg-3';
const TD = 'border-b border-line px-3.5 py-2.5 whitespace-nowrap';

export default function ActivityPage() {
  const { rows, loading, loadingMore, error, hasMore, fetch, loadMore, loadAll } =
    useActivityStore();
  const [filter, setFilter] = useState<ActivityFilter>('all');
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    fetch();
  }, [fetch]);

  const shown = useMemo(
    () => (filter === 'all' ? rows : rows.filter((r) => r.group === filter)),
    [rows, filter]
  );
  const months = useMemo(() => groupByMonth(shown, statementFlow), [shown]);
  const firstLoad = loading && rows.length === 0;

  const exportCsv = async () => {
    setExporting(true);
    const complete = hasMore ? await loadAll() : true;
    setExporting(false);
    if (!complete) return;
    const all = useActivityStore.getState().rows;
    const picked = filter === 'all' ? all : all.filter((r) => r.group === filter);
    download(activityCsv(picked, typeOfKind));
  };

  return (
    <div className="page">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
        <div className="min-w-0">
          <Link
            to="/portfolio"
            className="inline-flex items-center gap-1 text-[12.5px] text-fg-3 hover:text-fg max-md:text-[15px] max-md:text-accent"
          >
            <ChevronLeft className="h-4 w-4 md:hidden" />
            Portfolio <span className="max-md:hidden">/</span>
          </Link>
          <h1 className="m-0 text-[22px] font-semibold tracking-[-0.02em] max-md:mt-1.5 max-md:text-2xl">
            Activity
          </h1>
          <div className="mt-0.5 text-[13px] text-fg-3">
            Deposits, allocations, trades and income on the paper account
          </div>
        </div>
        <div className="flex max-w-full flex-wrap items-center gap-2">
          <div className="no-scrollbar max-w-full overflow-x-auto">
            <Segmented
              label="Show"
              options={ACTIVITY_FILTERS}
              value={filter}
              onChange={setFilter}
            />
          </div>
          <button
            type="button"
            className="btn btn-secondary max-md:hidden"
            onClick={exportCsv}
            disabled={exporting || rows.length === 0}
          >
            <Download className="h-3.5 w-3.5" />
            {exporting ? 'Preparing…' : 'Export CSV'}
          </button>
        </div>
      </div>

      <div className="panel overflow-hidden">
        {firstLoad ? (
          <div aria-busy="true">
            <LoadingLabel>Loading activity</LoadingLabel>
            <SkeletonRows rows={8} cols={4} />
          </div>
        ) : error && rows.length === 0 ? (
          <PanelError
            title="Activity couldn't be loaded"
            cause={causeSentence(error)}
            unaffected="Your balances and sleeves aren't affected."
            onRetry={() => fetch()}
            retrying={loading}
          />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={Receipt}
            title="No activity yet"
            body="Paper deposits, allocations to sleeves, trades and income appear here as the ledger records them."
          />
        ) : shown.length === 0 ? (
          <NoMatch
            noun="entries"
            filters={[ACTIVITY_FILTERS.find((f) => f.key === filter)?.label ?? '']}
            total={rows.length}
            onClear={() => setFilter('all')}
          />
        ) : (
          <>
            <table className="w-full border-collapse text-[13px] max-md:hidden">
              <thead>
                <tr>
                  <th className={TH}>Date</th>
                  <th className={TH}>Entry</th>
                  <th className={TH}>Detail</th>
                  <th className={TH}>Type</th>
                  <th className={`${TH} text-right`}>Paid in</th>
                  <th className={`${TH} text-right`}>Paid out</th>
                </tr>
              </thead>
              {months.map((m) => (
                <tbody key={m.key}>
                  <tr>
                    <td
                      colSpan={6}
                      className="border-b border-line bg-sunk px-3.5 py-1.5 font-mono text-[11px] font-medium text-fg-3"
                    >
                      {m.label}
                    </td>
                  </tr>
                  {m.rows.map((r) => {
                    const f = statementFlow(r);
                    return (
                      <tr key={r.id}>
                        <td className={`${TD} num text-fg-3`}>{when(r.at)}</td>
                        <td className={TD}>{r.label}</td>
                        <td className={`${TD} max-w-[320px] truncate text-fg-2`}>{r.sublabel}</td>
                        <td className={`${TD} text-fg-3`}>{TYPE_LABEL[r.group]}</td>
                        <td className={`${TD} text-right`}>
                          {f.paidIn ? <Num value={f.paidIn} /> : null}
                        </td>
                        <td className={`${TD} text-right`}>
                          {f.paidOut ? <Num value={f.paidOut} /> : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              ))}
            </table>

            <div className="md:hidden">
              {months.map((m) => (
                <div key={m.key}>
                  <div className="kicker border-b border-line bg-sunk px-4 py-1.5">{m.label}</div>
                  {m.rows.map((r) => {
                    const f = statementFlow(r);
                    return (
                      <div
                        key={r.id}
                        className="flex items-center justify-between gap-3 border-b border-line px-4 py-3 text-[14.5px]"
                      >
                        <span className="min-w-0">
                          {r.label}
                          <span className="block truncate text-[12.5px] text-fg-3">
                            {[when(r.at), r.sublabel].filter(Boolean).join(' · ')}
                          </span>
                        </span>
                        {f.paidIn ? (
                          <Num value={f.paidIn} signed />
                        ) : f.paidOut ? (
                          <Num value={-f.paidOut} />
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>

            {(hasMore || error) && (
              <div className="flex items-center justify-between gap-3 px-3.5 py-3">
                <span className="text-[12.5px] text-fg-3">
                  {error
                    ? `More entries couldn't be loaded. ${causeSentence(error)}`
                    : 'Older entries are available.'}
                </span>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => loadMore()}
                  disabled={loadingMore}
                >
                  {loadingMore ? 'Loading…' : error ? 'Try again' : 'Load more'}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
