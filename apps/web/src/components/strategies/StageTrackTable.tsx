import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { dayLabel, type SessionRow } from '../sessions/sessionRows';
import { Money, Pct, Skeleton } from '../ui';

import {
  editedAt,
  nextStage,
  STAGE_HEAD,
  STAGES,
  stageRow,
  strategySub,
  TRACK_COLS,
  type Stage,
  type StageRow,
} from './stageModel';
import { useLazyRun } from './useLazyRun';

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const shortDate = (d: Date) => `${MON[d.getMonth()]} ${d.getDate()}`;

type Mark = 'passed' | 'current' | 'stopped' | 'live' | 'next' | 'later';

function markFor(row: StageRow, stage: Stage): Mark {
  const at = STAGES.indexOf(row.stage);
  const i = STAGES.indexOf(stage);
  if (i < at) return 'passed';
  if (i === at) {
    const s = stage === 'live' ? row.live : stage === 'paper' ? row.paper : null;
    if (s && !s.view.open) return 'stopped';
    return stage === 'live' ? 'live' : 'current';
  }
  if (nextStage(row) === stage) return 'next';
  return 'later';
}

const MARK_CLASS: Record<Mark, string> = {
  passed: 'h-[11px] w-[11px] rounded-full border-[1.5px] border-accent bg-panel',
  current: 'h-[11px] w-[11px] rounded-full bg-accent',
  live: 'h-[11px] w-[11px] rounded-full bg-fg',
  stopped: 'h-[10px] w-[10px] rounded-[2px] bg-fg-3',
  next: 'h-[11px] w-[11px] rounded-full border-[1.5px] border-dashed border-fg-3 bg-panel',
  later: 'h-[5px] w-[5px] rounded-full bg-fg-3/40 ml-[3px]',
};

/** The line leaving a stage toward the next column. */
function segment(row: StageRow, stage: Stage): 'solid' | 'dashed' | null {
  const at = STAGES.indexOf(row.stage);
  const i = STAGES.indexOf(stage);
  if (i < at) return 'solid';
  if (i === at && nextStage(row) === STAGES[i + 1]) return 'dashed';
  return null;
}

function TrackPoint({ row, stage }: { row: StageRow; stage: Stage }) {
  const seg = segment(row, stage);
  const last = stage === 'live';
  return (
    <span aria-hidden="true" className="relative mb-2.5 flex h-[11px] items-center">
      {seg && !last && (
        <i
          className={`absolute left-[6px] right-[-26px] top-1/2 ${
            seg === 'solid'
              ? 'border-t-[1.5px] border-accent/70'
              : 'border-t-[1.5px] border-dashed border-fg-3/60'
          }`}
        />
      )}
      <i className={`relative block flex-none ${MARK_CLASS[markFor(row, stage)]}`} />
    </span>
  );
}

const Sub = ({ children }: { children: ReactNode }) => (
  <span className="mt-0.5 block truncate text-[11.5px] text-fg-3">{children}</span>
);

function SessionCell({ s, stage }: { s: SessionRow; stage: 'paper' | 'live' }) {
  const since = s.startedAt ? shortDate(s.startedAt) : '';
  const total = s.figures.totalPct;
  if (!s.view.open) {
    const ended = s.session.endedAt?.seconds
      ? new Date(Number(s.session.endedAt.seconds) * 1000)
      : null;
    return (
      <>
        <b className="font-mono text-[13.5px] font-medium">
          Stopped{ended ? ` ${shortDate(ended)}` : ''}
        </b>
        <Sub>
          {total !== null && <Pct value={total} pnl dp={1} />}
          {total !== null && since ? ` from ${since}` : since ? `Started ${since}` : ''}
        </Sub>
      </>
    );
  }
  return (
    <>
      <b className="font-mono text-[14px] font-medium">
        {s.figures.equity !== null ? <Money value={s.figures.equity} /> : s.view.label}
      </b>
      <Sub>
        {total !== null && <Pct value={total} pnl dp={1} />}
        {total !== null ? ` since ${since}` : since ? `Since ${since}` : ''}
        {stage === 'paper' ? ' in paper' : ''}
      </Sub>
    </>
  );
}

function StageCell({ row, stage, strategy }: { row: StageRow; stage: Stage; strategy: Strategy }) {
  let body: ReactNode = null;
  if (stage === 'draft') {
    const edited = editedAt(strategy);
    body = (
      <>
        <b className="font-mono text-[13.5px] font-medium">v{strategy.version || 1}</b>
        <Sub>{edited ? `Edited ${shortDate(edited)}` : 'Not saved yet'}</Sub>
      </>
    );
  } else if (stage === 'backtested') {
    const b = row.backtest;
    if (b.kind === 'loading') body = <Skeleton className="h-3 w-16" />;
    else if (b.kind === 'none') body = <Sub>Not backtested yet</Sub>;
    else {
      const f = b.figures;
      body =
        b.kind === 'current' ? (
          <>
            <b className="font-mono text-[13.5px] font-medium">
              <Pct value={f.totalReturn} pnl dp={1} />
            </b>
            <Sub>
              {f.benchmarkReturn !== null &&
                `${f.benchmarkSymbol} ${f.benchmarkReturn >= 0 ? '+' : '−'}${Math.abs(f.benchmarkReturn * 100).toFixed(1)}% · `}
              Sharpe {f.sharpe.toFixed(2)}
            </Sub>
          </>
        ) : (
          <>
            <b className="font-mono text-[13.5px] font-medium text-fg-3">
              <Pct value={f.totalReturn} dp={1} signed />
            </b>
            <Sub>From v{b.version}. Rules changed since.</Sub>
          </>
        );
    }
  } else {
    const s = stage === 'live' ? row.live : row.paper;
    if (s) body = <SessionCell s={s} stage={stage} />;
    else if (stage === 'paper' && row.stage === 'backtested') body = <Sub>Never run</Sub>;
    else if (stage === 'live' && row.stage === 'paper') body = <Sub>Not live</Sub>;
  }
  return (
    <div className={`h-full min-w-0 px-3 py-3.5 ${stage === 'live' ? 'bg-sunk/70' : ''}`}>
      <TrackPoint row={row} stage={stage} />
      {body}
    </div>
  );
}

interface NextProps {
  row: StageRow;
  strategy: Strategy;
  today: Date;
  onDeploy: (s: Strategy) => void;
}

export function NextCell({ row, strategy, today, onDeploy }: NextProps) {
  const n = row.next;
  switch (n.kind) {
    case 'rebalance':
      return (
        <span className="text-right">
          <b className="block font-mono text-[13px] font-medium">
            {n.at.getTime() === today.getTime() ? 'Today' : dayLabel(n.at)}
          </b>
          <Sub>Next rebalance</Sub>
        </span>
      );
    case 'schedule':
      return n.label ? (
        <span className="text-right">
          <b className="block text-[12.5px] font-medium">{n.label}</b>
          <Sub>Rebalances</Sub>
        </span>
      ) : null;
    case 'restart':
    case 'start':
      return (
        <button
          type="button"
          onClick={() => onDeploy(strategy)}
          className="btn btn-secondary btn-sm relative z-10"
        >
          {n.kind === 'start' ? 'Start in paper' : 'Restart in paper'}
        </button>
      );
    case 'backtest':
      return (
        <Link
          to={`/backtest?strategy=${strategy.id}`}
          className="btn btn-secondary btn-sm relative z-10"
        >
          Backtest v{n.version}
        </Link>
      );
    case 'firstBacktest':
      return (
        <Link
          to={`/backtest?strategy=${strategy.id}`}
          className="btn btn-primary btn-sm relative z-10"
        >
          Run a backtest
        </Link>
      );
    default:
      return null;
  }
}

interface RowProps {
  strategy: Strategy;
  sessions: readonly SessionRow[];
  today: Date;
  onDeploy: (s: Strategy) => void;
}

/** One strategy on the track: a column per stage, the next step at the end. */
export function StageTrackRow({ strategy, sessions, today, onDeploy }: RowProps) {
  const { ref, run } = useLazyRun(strategy.id);
  const row = stageRow(strategy, run, sessions, today);
  return (
    <div
      ref={ref}
      role="row"
      className={`relative grid ${TRACK_COLS} items-stretch border-t border-line hover:bg-sunk/40`}
    >
      <div role="rowheader" className="min-w-0 px-5 py-3.5">
        <Link
          to={`/strategies/${strategy.id}`}
          className="block truncate text-[14px] font-semibold after:absolute after:inset-0 hover:text-accent"
        >
          {strategy.name}
        </Link>
        <Sub>{strategySub(strategy)}</Sub>
      </div>
      {STAGES.map((s) => (
        <div role="cell" key={s} className="flex min-w-0">
          <div className="min-w-0 flex-1">
            <StageCell row={row} stage={s} strategy={strategy} />
          </div>
        </div>
      ))}
      <div role="cell" className="flex items-center justify-end px-5 py-3.5">
        <NextCell row={row} strategy={strategy} today={today} onDeploy={onDeploy} />
      </div>
    </div>
  );
}

/** The phone row: the four stages as dots, the current figure and the next step. */
export function StageTrackPhoneRow({ strategy, sessions, today, onDeploy }: RowProps) {
  const { ref, run } = useLazyRun(strategy.id);
  const row = stageRow(strategy, run, sessions, today);
  const s = row.live ?? row.paper;
  return (
    <div ref={ref} className="relative grid gap-2 border-t border-line px-4 py-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            to={`/strategies/${strategy.id}`}
            className="block truncate text-[14.5px] font-semibold after:absolute after:inset-0"
          >
            {strategy.name}
          </Link>
          <Sub>{strategySub(strategy)}</Sub>
        </div>
        <span className="flex-none text-right font-mono text-[13px]">
          {s && s.view.open && s.figures.equity !== null ? (
            <Money value={s.figures.equity} />
          ) : row.backtest.kind === 'current' ? (
            <Pct value={row.backtest.figures.totalReturn} pnl dp={1} />
          ) : null}
        </span>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-1.5 text-[11.5px] text-fg-3">
          {STAGES.map((st) => (
            <i
              key={st}
              aria-hidden="true"
              className={`block flex-none ${MARK_CLASS[markFor(row, st)]}`}
            />
          ))}
          <span className="ml-1.5">{STAGE_HEAD[row.stage].title}</span>
        </span>
        <NextCell row={row} strategy={strategy} today={today} onDeploy={onDeploy} />
      </div>
    </div>
  );
}

/** The column headings, shared by the list and the empty track. */
export function StageTrackHead({ next = true }: { next?: boolean }) {
  return (
    <div role="row" className={`grid ${TRACK_COLS} border-b border-line bg-sunk/60`}>
      <div role="columnheader" className="px-5 py-3">
        <span className="kicker">Strategy</span>
        <Sub>Rebalance · symbols</Sub>
      </div>
      {STAGES.map((s) => (
        <div role="columnheader" key={s} className="min-w-0 px-3 py-3">
          <span className="kicker">{STAGE_HEAD[s].title}</span>
          <Sub>{STAGE_HEAD[s].sub}</Sub>
        </div>
      ))}
      <div role="columnheader" className="px-5 py-3 text-right">
        {next && <span className="kicker">Next</span>}
      </div>
    </div>
  );
}
