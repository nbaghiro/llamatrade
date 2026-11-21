import {
  BacktestStatus,
  type BacktestMetrics,
  type BacktestRun,
} from '@llamatrade/core/proto/backtest_pb';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';
import type { CSSProperties } from 'react';

import { monthTicks, pinAlign, tickLabel, timeFraction } from '../../lib/chart/timeScale';
import { formatNumber, formatPct } from '../../lib/format';
import { LaneLegend, LaneMarker } from '../charts';
import { Pct } from '../ui/Num';

import { aheadOfPrevious, laneSubtitle, sessionBarLabel, versionResults } from './historyLanes';
import { timelineWindow, type StrategyRow } from './historyTimeline';
import { strategyNameOf } from './runLabels';
import { latestSession, type StrategySession } from './strategySessions';

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const shortDay = (d: Date) => `${MON[d.getMonth()]} ${d.getDate()}`;
const at = (f: number): CSSProperties => ({ left: `${(f * 100).toFixed(3)}%` });
const SHIFT = { start: '0%', center: '-50%', end: '-100%' } as const;

/** A run's return, or null when its metrics aren't loaded. */
function returnOf(metrics: Record<string, BacktestMetrics>, run: BacktestRun): number | null {
  const m = metrics[run.id];
  return m ? toNumber(m.totalReturn) : null;
}

/** Version labels closer than this (a fraction of the lane) to an earlier label are left out. */
const LABEL_GAP = 0.14;

/**
 * One lane per strategy across the calendar, a mark for every run on the day it was made, the
 * paper or live session as a bar from the day it started, and the latest result beside it
 * (history2 A). Selecting a lane filters the run list under it.
 */
export function StrategyTimeline({
  rows,
  metrics,
  strategies,
  selected,
  onSelect,
  today,
  sessions = [],
}: {
  rows: readonly StrategyRow[];
  metrics: Record<string, BacktestMetrics>;
  strategies: readonly Strategy[];
  selected: string;
  onSelect: (strategyId: string) => void;
  today: Date;
  sessions?: readonly StrategySession[];
}) {
  const win = timelineWindow(rows, today);
  if (!win) return null;
  const statuses = rows.flatMap((r) => r.runs.map((x) => x.run.status));
  const anyRunning = statuses.some(
    (st) => st === BacktestStatus.RUNNING || st === BacktestStatus.PENDING
  );
  const anyFailed = statuses.some(
    (st) => st === BacktestStatus.FAILED || st === BacktestStatus.CANCELLED
  );
  const firstRun = new Date(Math.min(...rows.map((r) => r.runs[0].at.getTime())));
  const span = (win.end.getTime() - win.start.getTime()) / 86_400_000;
  const fx = (d: Date) => timeFraction(d, win.start, win.end);
  const ticks = monthTicks(win.start, win.end, 6);

  return (
    <div className="min-w-0">
      <div className="grid grid-cols-[minmax(170px,230px)_minmax(0,1fr)_200px] border-b border-line text-[11px] font-medium text-fg-3">
        <div className="px-3.5 py-2">Strategy · runs from {shortDay(firstRun)}</div>
        <div />
        <div className="border-l border-line px-3.5 py-2">Latest result · backtest</div>
      </div>
      <ul className="m-0 list-none p-0">
        {rows.map((row) => {
          const name = strategyNameOf(strategies, row.strategyId);
          const on = selected === row.strategyId;
          const latest = row.latestCompleted;
          const latestRet = latest ? returnOf(metrics, latest.run) : null;
          const failedLast =
            row.latest.run.status === BacktestStatus.FAILED ||
            row.latest.run.status === BacktestStatus.CANCELLED;
          const m = latest ? metrics[latest.run.id] : undefined;
          const session = latestSession(sessions, row.strategyId);
          const ahead = aheadOfPrevious(row, metrics);
          const sessionFrom = session?.startedAt ? Math.max(0, fx(session.startedAt)) : null;
          const sessionTo = session
            ? Math.min(1, fx(session.active ? today : (session.stoppedAt ?? today)))
            : null;
          const labelled: number[] = sessionFrom !== null ? [sessionFrom] : [];
          const versionLabels = versionResults(row)
            .reverse()
            .filter((r) => {
              const f = fx(r.at);
              if (labelled.some((x) => Math.abs(x - f) < LABEL_GAP)) return false;
              labelled.push(f);
              return true;
            })
            .slice(0, 3);
          return (
            <li key={row.strategyId}>
              <button
                type="button"
                aria-pressed={on}
                onClick={() => onSelect(on ? '' : row.strategyId)}
                className={`grid w-full grid-cols-[minmax(170px,230px)_minmax(0,1fr)_200px] border-b border-line text-left last:border-b-0 hover:bg-sunk/60 ${
                  on ? 'bg-accent-soft' : ''
                }`}
              >
                <span className="min-w-0 px-3.5 py-3">
                  <span className="block truncate text-[12.5px] font-semibold">{name}</span>
                  <span className="block truncate text-[11px] text-fg-3">
                    {laneSubtitle(row, session)}
                  </span>
                </span>
                <span className="relative min-w-0">
                  {session &&
                    sessionFrom !== null &&
                    sessionTo !== null &&
                    sessionTo > sessionFrom && (
                      <>
                        <i
                          aria-hidden="true"
                          className={`absolute top-[60%] mt-[3px] h-[5px] rounded-[2px] border-l-2 ${
                            !session.active
                              ? 'border-fg-3 bg-fg-3/25'
                              : session.mode === 'live'
                                ? 'border-fg bg-fg/75'
                                : 'border-accent bg-accent/25'
                          }`}
                          style={{
                            ...at(sessionFrom),
                            width: `${((sessionTo - sessionFrom) * 100).toFixed(3)}%`,
                          }}
                        />
                        <span
                          className="absolute top-1.5 whitespace-nowrap rounded-full border border-line-strong bg-panel px-1.5 font-mono text-[10px] leading-[15px] text-fg-2"
                          style={{
                            ...at(sessionFrom),
                            transform: `translateX(${SHIFT[pinAlign(sessionFrom)]})`,
                          }}
                        >
                          {sessionBarLabel(session)}
                        </span>
                      </>
                    )}
                  <i
                    aria-hidden="true"
                    className="absolute top-[60%] border-t border-line-strong"
                    style={{
                      ...at(fx(row.runs[0].at)),
                      width: `${((fx(row.latest.at) - fx(row.runs[0].at)) * 100).toFixed(3)}%`,
                    }}
                  />
                  {row.runs.map((r) => {
                    const st = r.run.status;
                    const shape = st === BacktestStatus.COMPLETED ? 'ring' : 'dot';
                    const tone =
                      st === BacktestStatus.FAILED || st === BacktestStatus.CANCELLED
                        ? 'risk'
                        : 'accent';
                    const ret = returnOf(metrics, r.run);
                    return (
                      <span
                        key={r.run.id}
                        className="absolute inset-x-0 top-[60%] h-0"
                        aria-hidden="true"
                      >
                        <LaneMarker
                          shape={shape}
                          tone={tone}
                          positioned
                          style={at(fx(r.at))}
                          title={`v${r.run.strategyVersion} · ${shortDay(r.at)}${ret !== null ? ` · ${formatPct(ret, { dp: 1, signed: true })}` : ''}`}
                        />
                      </span>
                    );
                  })}
                  {versionLabels.map((r) => {
                    const f = fx(r.at);
                    const ret = returnOf(metrics, r.run);
                    return (
                      <span
                        key={r.run.id}
                        className="absolute top-1.5 whitespace-nowrap font-mono text-[10.5px] text-fg-2"
                        style={{ ...at(f), transform: `translateX(${SHIFT[pinAlign(f)]})` }}
                      >
                        v{r.run.strategyVersion}
                        {ret !== null && (
                          <b className="ml-1 font-semibold text-fg">
                            {formatPct(ret, { dp: 1, signed: true })}
                          </b>
                        )}
                      </span>
                    );
                  })}
                </span>
                <span className="min-w-0 border-l border-line px-3.5 py-2.5">
                  {latest && latestRet !== null ? (
                    <>
                      <span className="block font-mono text-[13px]">
                        <Pct value={latestRet} pnl dp={1} />{' '}
                        <span className="text-[11px] text-fg-3">
                          v{latest.run.strategyVersion} · {shortDay(latest.at)}
                        </span>
                      </span>
                      <span className="block truncate text-[11px] text-fg-3">
                        {failedLast
                          ? `v${row.latest.run.strategyVersion} after it couldn't finish`
                          : ahead
                            ? `${formatNumber(Math.abs(ahead.points), { dp: 1 })} pts ${ahead.points >= 0 ? 'ahead of' : 'behind'} v${ahead.version}, same settings`
                            : m
                              ? `Worst fall ${formatPct(-Math.abs(toNumber(m.maxDrawdown)), { dp: 1 })}`
                              : ''}
                      </span>
                    </>
                  ) : failedLast ? (
                    <>
                      <span className="block text-[12.5px] text-risk">Couldn&apos;t finish</span>
                      <span className="block truncate text-[11px] text-fg-3">
                        {row.latest.run.statusMessage || 'No finished run yet'}
                      </span>
                    </>
                  ) : (
                    <span className="block text-[12px] text-fg-3">No finished run yet</span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <div className="grid grid-cols-[minmax(170px,230px)_minmax(0,1fr)_200px] border-t border-line">
        <div />
        <div className="relative h-7">
          {ticks.map((t) => {
            const f = fx(t);
            if (f > 0.9) return null;
            return (
              <span
                key={t.getTime()}
                className="absolute top-[7px] whitespace-nowrap px-1 font-mono text-[10.5px] text-fg-3"
                style={{ ...at(f), transform: `translateX(${SHIFT[pinAlign(f)]})` }}
              >
                {tickLabel(t, span)}
              </span>
            );
          })}
          <span
            className="absolute top-[7px] whitespace-nowrap px-1 font-mono text-[10.5px] text-fg-3"
            style={{ ...at(fx(today)), transform: 'translateX(-100%)' }}
          >
            Today
          </span>
        </div>
        <div className="flex items-center border-l border-line px-3.5">
          <LaneLegend
            items={[
              { shape: 'ring', label: 'Run' },
              ...(anyRunning ? [{ shape: 'dot' as const, label: 'Running' }] : []),
              ...(anyFailed
                ? [{ shape: 'dot' as const, label: 'Failed', tone: 'risk' as const }]
                : []),
              ...(sessions.length ? [{ shape: 'start' as const, label: 'Session' }] : []),
            ]}
            className="flex-nowrap gap-x-2.5"
          />
        </div>
      </div>
    </div>
  );
}
