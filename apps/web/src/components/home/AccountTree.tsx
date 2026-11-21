import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { formatMoney } from '../../lib/format';
import { ancestors, collapse, guidesOf, phraseParts, withKids } from '../../lib/outlineTree';
import { Parts } from '../strategy-builder/outline/Outline';
import { LiveMarker, Ticker, TreeBar, TreeRow } from '../ui';

import type { HomeRow } from './accountRows';
import { signedPct, toneText } from './homeModel';
import { HomeCard } from './HomePanels';
import type { MonthLine } from './perfModel';

const HEAD = ['Share', '1M vs SPY', '1M', 'Value', 'Today'];
const COLS = 'grid grid-cols-[128px_96px_60px_108px_88px] items-center gap-x-3';

export function Spark({ month, muted }: { month: MonthLine; muted?: boolean }) {
  const { acc, spy } = month;
  if (acc.length < 2) return <span />;
  const W = 72;
  const H = 22;
  const vals = [...acc, ...(spy ?? [])];
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const x = (i: number) => (i / (acc.length - 1)) * W;
  const y = (v: number) => H - 2 - ((v - lo) / (hi - lo || 1)) * (H - 4);
  const path = (l: readonly number[]) =>
    l.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      aria-hidden="true"
      className="block h-[22px] w-[72px] justify-self-end overflow-visible"
    >
      {spy && (
        <path
          d={path(spy)}
          className="fill-none stroke-fg-3 [stroke-dasharray:2_2] [stroke-width:1]"
        />
      )}
      <path
        d={path(acc)}
        className={`fill-none [stroke-linejoin:round] [stroke-width:1.3] ${muted ? 'stroke-fg-3' : 'stroke-fg'}`}
      />
      <circle cx={x(acc.length - 1)} cy={y(acc[acc.length - 1])} r="1.8" className="fill-fg" />
    </svg>
  );
}

function Cells({ r, month }: { r: HomeRow; month: MonthLine | null }) {
  const lead =
    r.liveMarker || r.note ? (
      <span className="col-span-3 justify-self-end whitespace-nowrap text-[12.5px] text-fg-3">
        {r.liveMarker ? <LiveMarker /> : r.note}
      </span>
    ) : (
      <>
        {r.share !== undefined ? (
          <span className="flex items-center justify-end gap-2">
            <TreeBar pct={r.share} width={58} live={r.live} muted={r.muted} />
            <span className="w-[42px] text-right font-mono text-[12px] font-medium text-fg">
              {r.share.toFixed(1)}%
            </span>
          </span>
        ) : (
          <span />
        )}
        {month ? <Spark month={month} muted={r.muted} /> : <span />}
        <span className="whitespace-nowrap text-right font-mono text-[12px] text-fg-2">
          {month?.ret === null || month?.ret === undefined ? '' : signedPct(month.ret, 1)}
        </span>
      </>
    );
  const strong = r.kind === 'account' ? 'font-medium' : '';
  return (
    <span className={COLS}>
      {lead}
      <span
        className={`whitespace-nowrap text-right font-mono text-[13px] tabular-nums ${r.muted ? 'text-fg-3' : 'text-fg'} ${strong}`}
      >
        {r.value === undefined ? '' : formatMoney(r.value)}
      </span>
      {r.today !== undefined && r.today !== null ? (
        <span
          className={`whitespace-nowrap text-right font-mono text-[13px] tabular-nums ${toneText(r.today)} ${strong}`}
        >
          {formatMoney(r.today, { signed: true })}
        </span>
      ) : (
        <span className="whitespace-nowrap text-right text-[12px] text-fg-3">
          {r.na ?? (r.today === null ? 'No figure' : '')}
        </span>
      )}
    </span>
  );
}

function Phrase({ r }: { r: HomeRow }) {
  if (r.kind === 'asset')
    return (
      <>
        <Ticker symbol={r.symbol ?? ''} /> {r.label && <span className="text-fg-3">{r.label}</span>}
      </>
    );
  if (r.kind === 'rule' && r.parts && r.outlineKind)
    return <Parts parts={phraseParts(r.outlineKind, r.parts)} />;
  return (
    <>
      {r.label}
      {r.sub && <span className="ml-1 text-[12.5px] font-normal text-fg-3">{r.sub}</span>}
    </>
  );
}

const PHRASE: Partial<Record<HomeRow['kind'], string>> = {
  account: 'text-[14.5px] font-semibold tracking-[-0.01em]',
  mode: 'font-medium',
  session: 'text-[14px] font-medium',
};

export interface AccountTreeProps {
  rows: readonly HomeRow[];
  months: ReadonlyMap<string, MonthLine>;
  hover: string | null;
  pin: string | null;
  /** A session hovered elsewhere on Home. */
  hotSession: string | null;
  onHover: (id: string | null) => void;
  onPin: (id: string | null) => void;
}

/** home/tree: the account as an outline in the builder's tree style, with figures per row. */
export function AccountTree({
  rows,
  months,
  hover,
  pin,
  hotSession,
  onHover,
  onPin,
}: AccountTreeProps) {
  const navigate = useNavigate();
  const [closed, setClosed] = useState<ReadonlySet<string>>(new Set());
  const flat = useMemo(() => withKids(rows), [rows]);
  const holders = flat.filter((r, i) => r.kids && flat[i + 1]?.kind === 'asset');
  const allClosed = holders.length > 0 && holders.every((r) => closed.has(r.id));
  const active = hover ?? pin;
  const path = useMemo(
    () => (active ? ancestors(rows, active) : new Set<string>()),
    [rows, active]
  );
  const shown = collapse(
    flat.map((r) => ({ ...r, live: r.live || path.has(r.id) })),
    closed
  );
  const guides = guidesOf(shown);
  const anyLive = rows.some((r) => r.liveMarker);
  const anyFrozen = rows.some((r) => r.warn);
  const toggle = (id: string) =>
    setClosed((c) => {
      const next = new Set(c);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <HomeCard
      title="Your account"
      sub="By mode and session"
      right={
        holders.length > 0 && (
          <button
            type="button"
            onClick={() => setClosed(allClosed ? new Set() : new Set(holders.map((r) => r.id)))}
            className="font-mono text-[10.5px] font-medium uppercase tracking-[0.08em] text-fg-2 hover:text-fg"
          >
            {allClosed ? 'Show holdings' : 'Collapse holdings'}
          </button>
        )
      }
    >
      <div onMouseLeave={() => onHover(null)}>
        <div className="flex h-[34px] items-center border-b border-line pr-4 font-mono text-[10.5px] font-medium uppercase leading-none tracking-[0.08em] text-fg-3">
          <span className="flex-1 pl-[30px]">Account, session and holding</span>
          <span className={`ml-3 ${COLS}`}>
            {HEAD.map((h) => (
              <span key={h} className="text-right">
                {h}
              </span>
            ))}
          </span>
        </div>
        <div role="tree" aria-label="Your account" className="pb-2 pt-1.5">
          {shown.map((r, i) => {
            const onPath = r.lineKey !== undefined;
            return (
              <TreeRow
                key={r.id}
                role="treeitem"
                aria-level={r.depth + 1}
                guides={guides[i]}
                type={r.type}
                typeWidth={62}
                phraseClass={`text-[13.5px] ${PHRASE[r.kind] ?? ''}`}
                live={r.live}
                muted={r.muted}
                flag={r.warn ? 'warning' : undefined}
                hot={r.id === hover || (hotSession !== null && r.sessionId === hotSession)}
                pinned={r.id === pin}
                hiddenCount={r.hidden}
                closed={r.kids ? closed.has(r.id) : undefined}
                onToggle={() => toggle(r.id)}
                onMouseEnter={() => onHover(r.id)}
                onClick={() => {
                  if (r.href) navigate(r.href);
                  else if (onPath) onPin(pin === r.id ? null : r.id);
                }}
                end={
                  <Cells
                    r={r}
                    month={r.lineKey && r.kind !== 'rule' ? (months.get(r.lineKey) ?? null) : null}
                  />
                }
              >
                <Phrase r={r} />
              </TreeRow>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-t border-line px-5 py-3 text-[12.5px] text-fg-3">
          {anyLive && (
            <span className="inline-flex items-center gap-2">
              <i aria-hidden="true" className="inline-block w-3.5 border-t-[1.5px] border-fg" />
              Branch in effect today
            </span>
          )}
          {anyFrozen && (
            <span className="inline-flex items-center gap-2">
              <span aria-hidden="true" className="font-mono text-risk">
                !
              </span>
              Waiting for your review
            </span>
          )}
          <span className="inline-flex items-center gap-2">
            <i
              aria-hidden="true"
              className="inline-block w-3.5 border-t border-dashed border-fg-3"
            />
            SPY
          </span>
          <span className="ml-auto">
            Hover a row to see its line on the chart. Click a session to open it.
          </span>
        </div>
      </div>
    </HomeCard>
  );
}
