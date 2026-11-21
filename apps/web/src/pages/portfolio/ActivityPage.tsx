import { useActivityStore, type ActivityRow } from '@llamatrade/core/stores/activity';
import { usePortfolioStore } from '@llamatrade/core/stores/portfolio';
import { Download, Receipt } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  ActivityLanes,
  type ActivityLane,
  type ActivityMark,
  type DateRange,
} from '../../components/portfolio/ActivityLanes';
import {
  accountsByRow,
  monthBounds,
  monthsWithEntries,
  OTHER_LANE,
  rowAccount,
  statementRows,
  totals,
  UNALLOCATED_LANE,
  type AccountKind,
  type StatementRow,
} from '../../components/portfolio/activityView';
import { byDay } from '../../components/portfolio/history';
import { sleeveColor } from '../../components/portfolio/sleeveView';
import {
  useAllActivity,
  useFillsByLedgerId,
  useResolvedSleeves,
  useSleeveFills,
} from '../../components/portfolio/usePortfolioData';
import {
  EmptyState,
  LoadingLabel,
  ModeBadge,
  Money,
  NoMatch,
  PageHead,
  PanelError,
  Segmented,
  SkeletonRows,
} from '../../components/ui';
import { formatMoney } from '../../lib/format';
import {
  ACTIVITY_FILTERS,
  activityCsv,
  causeSentence,
  type ActivityFilter,
  type FlowKind,
} from '../../lib/portfolioView';

const TYPE_LABEL: Record<ActivityRow['group'], string> = {
  funding: 'Funding',
  allocations: 'Allocations',
  trades: 'Trades',
  income: 'Income',
};

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
  a.download = `llamatrade-activity-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

const TIME = new Intl.DateTimeFormat('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});
const DAY = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' });
const MONTH = new Intl.DateTimeFormat('en-US', { month: 'short' });
const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;

const TH =
  'border-b border-line px-3.5 py-2.5 text-left font-mono text-[11px] font-medium uppercase tracking-[0.06em] text-fg-3';
const TD = 'border-b border-line px-3.5 py-2.5 whitespace-nowrap';
const ALL = 'all';

function Tag({ tag }: { tag: string }) {
  const solid = tag === 'IN' || tag === 'OUT';
  return (
    <span
      className={`inline-block min-w-[38px] rounded-[3px] px-1.5 py-px text-center font-mono text-[10.5px] ${
        solid ? 'bg-fg text-canvas' : 'border border-line-strong text-fg-2'
      }`}
    >
      {tag}
    </span>
  );
}

export default function ActivityPage() {
  const { rows, loading, error } = useAllActivity();
  const { fills } = useSleeveFills();
  const { sleeves: portfolioSleeves, loaded, fetchPortfolio } = usePortfolioStore();
  const sleeves = useResolvedSleeves(portfolioSleeves);
  const hasMore = useActivityStore((s) => s.hasMore);
  const loadMore = useActivityStore((s) => s.loadMore);
  const loadingMore = useActivityStore((s) => s.loadingMore);
  const [filter, setFilter] = useState<ActivityFilter>('all');
  const [lane, setLane] = useState<string>(ALL);
  const [account, setAccount] = useState<AccountKind | typeof ALL>(ALL);
  const [month, setMonth] = useState<string | null>(null);
  const [range, setRange] = useState<DateRange | null>(null);
  const [now] = useState(() => new Date());

  useEffect(() => {
    if (!loaded) fetchPortfolio();
  }, [loaded, fetchPortfolio]);

  const byLedgerId = useFillsByLedgerId(fills);
  const statement = useMemo(
    () => statementRows(rows, fills, sleeves, byLedgerId),
    [rows, fills, sleeves, byLedgerId]
  );
  const accounts = useMemo(() => accountsByRow(rows, sleeves), [rows, sleeves]);
  const accountOf = (r: StatementRow) => rowAccount(r, sleeves, accounts);
  const bothAccounts = new Set(sleeves.map((s) => s.live)).size > 1;
  const months = useMemo(() => monthsWithEntries(rows).slice(0, 3), [rows]);
  const activeMonth = month ?? months[0] ?? null;
  const span = useMemo(() => {
    if (activeMonth && activeMonth !== ALL) {
      const b = monthBounds(activeMonth);
      return { start: b.start, end: b.end < now ? b.end : now };
    }
    const first = rows.length ? rows[rows.length - 1].at : now;
    return { start: first, end: now };
  }, [activeMonth, rows, now]);

  const laneMeta = useMemo(() => {
    const list: { id: string; name: string; index: number; live?: boolean }[] = sleeves
      .map((s, index) => ({ id: s.sleeveId ?? s.executionId, name: s.name, index, live: s.live }))
      .filter((s) => s.id);
    list.push({ id: UNALLOCATED_LANE, name: 'Unallocated', index: -1 });
    if (statement.some((r) => r.lane === OTHER_LANE)) {
      list.push({ id: OTHER_LANE, name: 'Other', index: -1 });
    }
    return list;
  }, [sleeves, statement]);
  const nameOf = (id: string) => laneMeta.find((l) => l.id === id)?.name ?? 'Other';

  const inWindow = statement.filter((r) => r.row.at >= span.start && r.row.at <= span.end);
  const filtered = inWindow.filter(
    (r) =>
      (filter === 'all' || r.row.group === filter) &&
      (lane === ALL || r.lane === lane) &&
      (account === ALL || accountOf(r) === account) &&
      (!range || (r.row.at >= range.from && r.row.at <= range.to))
  );
  const sums = totals(filtered);

  const lanes: ActivityLane[] = laneMeta
    .filter((l) => lane === ALL || l.id === lane)
    .filter((l) => account === ALL || l.live === undefined || (account === 'live') === l.live)
    .map((l) => {
      const own = inWindow.filter((r) => r.lane === l.id);
      const trades = own.filter((r) => r.row.kind === 'buy' || r.row.kind === 'sell');
      const marks: ActivityMark[] = byDay(trades.map((r) => ({ at: r.row.at, r }))).map((d) => ({
        key: `f-${d.key}`,
        at: d.at,
        shape: 'dot',
        count: d.items.length,
        title: `${d.items.length} ${d.items.length === 1 ? 'fill' : 'fills'} on ${DAY.format(d.at)}`,
      }));
      for (const r of own) {
        if (r.row.kind === 'buy' || r.row.kind === 'sell') continue;
        marks.push({
          key: r.row.id,
          at: r.row.at,
          shape: r.row.kind === 'dividend' ? 'diamond' : 'diamondFilled',
          title: `${r.entry} ${formatMoney(r.row.amount)}`,
        });
      }
      if (l.id === UNALLOCATED_LANE) {
        for (const r of inWindow) {
          if (r.row.kind !== 'allocation') continue;
          marks.push({
            key: `out-${r.row.id}`,
            at: r.row.at,
            shape: 'diamond',
            tone: 'muted',
            title: `${formatMoney(r.row.amount)} out to ${nameOf(r.lane)}`,
          });
        }
      }
      return {
        id: l.id,
        label: (
          <span className="inline-flex min-w-0 items-center gap-1.5">
            <i
              aria-hidden="true"
              className={`h-2 w-2 flex-none rounded-[2px] ${l.index < 0 ? 'border border-dashed border-fg-3' : ''}`}
              style={l.index >= 0 ? { background: sleeveColor(l.index) } : undefined}
            />
            <span className="truncate">{l.name}</span>
          </span>
        ),
        badge:
          l.live === undefined ? undefined : (
            <ModeBadge mode={l.live ? 'live' : 'paper'} size="sm" />
          ),
        marks,
      };
    });

  const days: { key: string; label: string; rows: StatementRow<ActivityRow>[] }[] = [];
  for (const r of filtered) {
    const key = dayKey(r.row.at);
    const last = days[days.length - 1];
    if (last?.key === key) last.rows.push(r);
    else {
      const isToday = key === dayKey(now);
      days.push({ key, label: `${DAY.format(r.row.at)}${isToday ? ', today' : ''}`, rows: [r] });
    }
  }

  const heading = range
    ? `${DAY.format(range.from)} to ${DAY.format(range.to)}`
    : activeMonth === ALL
      ? 'All entries'
      : activeMonth
        ? new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric' }).format(
            monthBounds(activeMonth).start
          )
        : '';

  const firstLoad = loading && rows.length === 0;
  const sleeveName = (r: StatementRow) => (r.lane === OTHER_LANE ? '·' : nameOf(r.lane));
  const sleeveIndex = (r: StatementRow) => laneMeta.find((l) => l.id === r.lane)?.index ?? -1;

  return (
    <div className="page">
      <PageHead
        crumbs={[{ label: 'Portfolio', to: '/portfolio' }, { label: 'Activity' }]}
        title="Activity"
        sub="Every movement of money the ledger recorded: deposits, allocations, fills and income."
        actions={
          <>
            {months.length > 0 && (
              <Segmented
                label="Month"
                value={activeMonth ?? ALL}
                onChange={(m) => {
                  setMonth(m);
                  setRange(null);
                }}
                options={[
                  ...[...months]
                    .reverse()
                    .map((m) => ({ key: m, label: MONTH.format(monthBounds(m).start) })),
                  { key: ALL, label: 'All' },
                ]}
              />
            )}
            {bothAccounts && (
              <select
                aria-label="Account"
                value={account}
                onChange={(e) => {
                  const v = e.target.value;
                  setAccount(v === 'live' || v === 'paper' ? v : ALL);
                }}
                className="btn btn-secondary h-[34px] pr-7"
              >
                <option value={ALL}>Both accounts</option>
                <option value="live">Live</option>
                <option value="paper">Paper</option>
              </select>
            )}
            <select
              aria-label="Sleeve"
              value={lane}
              onChange={(e) => {
                setLane(e.target.value);
              }}
              className="btn btn-secondary h-[34px] pr-7"
            >
              <option value={ALL}>All sleeves</option>
              {laneMeta.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-secondary max-md:hidden"
              onClick={() =>
                download(
                  activityCsv(
                    filtered.map((r) => r.row),
                    typeOfKind
                  )
                )
              }
              disabled={filtered.length === 0}
            >
              <Download className="h-3.5 w-3.5" />
              CSV
            </button>
          </>
        }
      />

      {firstLoad ? (
        <div className="panel" aria-busy="true">
          <LoadingLabel>Loading activity</LoadingLabel>
          <SkeletonRows rows={8} cols={5} />
        </div>
      ) : error && rows.length === 0 ? (
        <div className="panel">
          <PanelError
            title="Activity couldn't be loaded"
            cause={causeSentence(error)}
            unaffected="Your balances and sleeves aren't affected."
            onRetry={() => useActivityStore.getState().fetch()}
            retrying={loading}
          />
        </div>
      ) : rows.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={Receipt}
            title="No activity yet"
            body="Paper deposits, allocations to sleeves, fills and income appear here as the ledger records them."
          />
        </div>
      ) : (
        <>
          <section className="panel-rim mb-4 px-5 pb-3 pt-4 max-md:hidden">
            <ActivityLanes
              lanes={lanes}
              start={span.start}
              end={span.end}
              range={range}
              onRange={setRange}
              rangeLabel={range ? `${heading} · ${filtered.length} entries` : undefined}
            />
          </section>

          <div className="mb-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <div className="flex flex-wrap items-baseline gap-x-3">
              <h2 className="m-0 text-[16px] font-semibold">{heading}</h2>
              <span className="text-[12px] text-fg-3 max-md:hidden">
                {range ? (
                  <button
                    type="button"
                    className="text-accent hover:underline"
                    onClick={() => setRange(null)}
                  >
                    Clear the range
                  </button>
                ) : (
                  'Drag on the lanes to choose a range'
                )}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <span className="num text-[12.5px] text-fg-2">
                In {formatMoney(sums.paidIn)} · out {formatMoney(sums.paidOut)}
              </span>
              <div className="no-scrollbar max-w-full overflow-x-auto">
                <Segmented
                  label="Show"
                  options={ACTIVITY_FILTERS}
                  value={filter}
                  onChange={setFilter}
                />
              </div>
            </div>
          </div>

          <div className="panel overflow-hidden">
            {filtered.length === 0 ? (
              <NoMatch
                noun="entries"
                filters={[
                  ACTIVITY_FILTERS.find((f) => f.key === filter)?.label ?? '',
                  lane === ALL ? '' : nameOf(lane),
                  account === ALL ? '' : account === 'live' ? 'Live' : 'Paper',
                  range ? heading : '',
                ].filter(Boolean)}
                total={inWindow.length}
                onClear={() => {
                  setFilter('all');
                  setLane(ALL);
                  setAccount(ALL);
                  setRange(null);
                }}
              />
            ) : (
              <>
                <table className="w-full border-collapse text-[13px] max-md:hidden">
                  <thead>
                    <tr>
                      <th className={TH}>Time</th>
                      <th className={TH}>Sleeve</th>
                      <th className={TH}>Kind</th>
                      <th className={TH}>Entry</th>
                      <th className={`${TH} text-right`}>In</th>
                      <th className={`${TH} text-right`}>Out</th>
                    </tr>
                  </thead>
                  {days.map((d) => (
                    <tbody key={d.key}>
                      <tr>
                        <td
                          colSpan={6}
                          className="border-b border-line px-3.5 pb-1.5 pt-3 text-[13px] font-medium"
                        >
                          {d.label}
                        </td>
                      </tr>
                      {d.rows.map((r) => {
                        const index = sleeveIndex(r);
                        return (
                          <tr key={r.row.id}>
                            <td className={`${TD} num text-fg-3`}>{TIME.format(r.row.at)}</td>
                            <td className={TD}>
                              <span className="inline-flex items-center gap-2">
                                {r.lane !== OTHER_LANE && (
                                  <i
                                    aria-hidden="true"
                                    className={`h-2 w-2 rounded-[2px] ${index < 0 ? 'border border-dashed border-fg-3' : ''}`}
                                    style={
                                      index >= 0 ? { background: sleeveColor(index) } : undefined
                                    }
                                  />
                                )}
                                {sleeveName(r)}
                              </span>
                            </td>
                            <td className={TD}>
                              <Tag tag={r.tag} />
                            </td>
                            <td className={`${TD} max-w-[360px] truncate`}>{r.entry}</td>
                            <td className={`${TD} text-right`}>
                              {r.paidIn ? <Money value={r.paidIn} /> : null}
                            </td>
                            <td className={`${TD} text-right`}>
                              {r.paidOut ? <Money value={r.paidOut} /> : null}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  ))}
                </table>

                <div className="md:hidden">
                  {days.map((d) => (
                    <div key={d.key}>
                      <div className="kicker border-b border-line bg-sunk px-4 py-1.5">
                        {d.label}
                      </div>
                      {d.rows.map((r) => (
                        <div
                          key={r.row.id}
                          className="flex items-center justify-between gap-3 border-b border-line px-4 py-3 text-[14.5px]"
                        >
                          <span className="min-w-0">
                            {r.entry}
                            <span className="block truncate text-[12.5px] text-fg-3">
                              {[TIME.format(r.row.at), sleeveName(r)]
                                .filter((x) => x !== '·')
                                .join(' · ')}
                            </span>
                          </span>
                          {r.paidIn ? (
                            <Money value={r.paidIn} signed />
                          ) : r.paidOut ? (
                            <Money value={-r.paidOut} />
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </>
            )}
            {hasMore && (
              <div className="flex items-center justify-between gap-3 px-3.5 py-3">
                <span className="text-[12.5px] text-fg-3">
                  {error
                    ? `More entries couldn't be loaded. ${causeSentence(error)}`
                    : 'Older entries are still loading.'}
                </span>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => loadMore()}
                  disabled={loadingMore}
                >
                  {loadingMore ? 'Loading…' : 'Load more'}
                </button>
              </div>
            )}
          </div>
          <p className="mt-2 text-[12px] text-fg-3">
            Fills are placed on the sleeve whose order made them. Dividends and entries the ledger
            doesn&apos;t tie to a sleeve are listed without one.
          </p>
        </>
      )}
    </div>
  );
}
