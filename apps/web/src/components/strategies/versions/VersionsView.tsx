import { num, toDate } from '@llamatrade/core/format';
import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import type { StrategyVersion } from '@llamatrade/core/proto/strategy_pb';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { formatPct } from '../../../lib/format';
import { buildOutline, metaParts } from '../../../lib/outline';
import { diffStrategies, type StrategySide } from '../../../lib/strategyDiff';
import { updateStrategy } from '../../../services/strategy';
import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import { useHandoffRun } from '../../strategy-builder/handoff/useHandoffRun';
import { Outline, Parts } from '../../strategy-builder/outline/Outline';
import { EmptyState, PanelError, Pct, Segmented, SkeletonRows } from '../../ui';
import { dayMonthYear, rangeLabel, runFigures } from '../strategyView';

import { CodeDiff } from './CodeDiff';
import { useRunPair, type useVersions } from './useVersions';

const VIEWS = [
  { key: 'outline', label: 'Outline' },
  { key: 'code', label: 'Code' },
] as const;

function side(v: StrategyVersion | undefined): StrategySide | null {
  if (!v) return null;
  const parsed = fromDSLString(v.dslCode);
  if (!parsed) return null;
  return {
    tree: parsed.tree,
    meta: {
      timeframe: parsed.metadata.timeframe ?? '1D',
      benchmark: parsed.metadata.benchmark ?? '',
    },
  };
}

function ResultChange({
  before,
  after,
  strategyId,
}: {
  before: BacktestRun;
  after: BacktestRun;
  strategyId: string;
}) {
  const handoff = useHandoffRun();
  const rerun = handoff.phase === 'done' && handoff.run ? handoff.run : null;
  const shown = rerun ?? after;
  const a = runFigures(before);
  const b = runFigures(shown);
  if (!a || !b) return null;
  const sameSetup =
    num(before.config?.initialCapital) === num(shown.config?.initialCapital) &&
    num(before.config?.commission) === num(shown.config?.commission) &&
    rangeLabel(a) === rangeLabel(b);
  const cell = (label: string, was: number, now: number, kind: 'return' | 'pct' | 'ratio') => (
    <div className="min-w-0 border-l border-line px-4 first:border-l-0 first:pl-0">
      <span className="kicker">{label}</span>
      <div className="mt-1 flex flex-wrap items-baseline gap-1.5 font-mono text-[15px]">
        <span className="text-[13px] text-fg-3">
          {kind === 'ratio' ? was.toFixed(2) : formatPct(was, { dp: 1, signed: true })} →
        </span>
        {kind === 'return' ? (
          <Pct value={now} pnl dp={1} />
        ) : (
          <span className="num">
            {kind === 'ratio' ? now.toFixed(2) : formatPct(now, { dp: 1, signed: true })}
          </span>
        )}
      </div>
    </div>
  );
  return (
    <div className="panel mt-5 px-4 py-3.5">
      <div className="grid grid-cols-3">
        {cell('Return', a.totalReturn, b.totalReturn, 'return')}
        {cell('Max drawdown', a.maxDrawdown, b.maxDrawdown, 'pct')}
        {cell('Sharpe', a.sharpe, b.sharpe, 'ratio')}
      </div>
      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2">
        <p className="m-0 text-[11.5px] text-fg-3">
          {sameSetup
            ? `Both backtests cover ${rangeLabel(b)} with the same capital and commission.`
            : `The two backtests used different ranges or settings (${rangeLabel(a)} and ${rangeLabel(b)}), so the figures don’t compare like for like.`}
          {handoff.phase === 'failed' && ` The new backtest didn’t finish: ${handoff.error ?? ''}`}
        </p>
        {!sameSetup && (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={handoff.phase === 'running'}
            onClick={() => handoff.start(strategyId, shown.strategyVersion, before)}
          >
            {handoff.phase === 'running'
              ? 'Backtesting…'
              : `Backtest version ${shown.strategyVersion} over the same dates`}
          </button>
        )}
      </div>
    </div>
  );
}

interface VersionsViewProps {
  strategyId: string;
  strategyName: string;
  /** The version a paper session runs, if any. */
  sessionVersion: number | null;
  /** The loaded versions and runs, from `useVersions`. */
  source: ReturnType<typeof useVersions>;
}

/** A timeline of saved versions beside the selected change, written as the outline with old wording struck. */
export function VersionsView({
  strategyId,
  strategyName,
  sessionVersion,
  source,
}: VersionsViewProps) {
  const { state, runs, reload } = source;
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<'outline' | 'code'>('outline');
  const [restoring, setRestoring] = useState(false);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const draft = useStrategyBuilderStore((s) =>
    s.strategyId === strategyId && s.isDirty ? { version: s.serverVersion + 1 } : null
  );

  const versions = state.status === 'ready' ? state.versions : [];
  const selectedNumber = Number(params.get('v')) || versions[0]?.version;
  const idx = versions.findIndex((v) => v.version === selectedNumber);
  const selected = idx >= 0 ? versions[idx] : versions[0];
  const defaultPrevious = idx >= 0 ? versions[idx + 1] : versions[1];
  const vsNumber = Number(params.get('vs'));
  const previous =
    versions.find((v) => v.version === vsNumber && v.version !== selected?.version) ??
    defaultPrevious;

  const diff = useMemo(() => {
    const after = side(selected);
    const before = side(previous);
    if (!after) return null;
    return before ? diffStrategies(before, after) : null;
  }, [selected, previous]);
  const firstOutline = useMemo(() => {
    const s = side(selected);
    return s ? { lines: buildOutline(s.tree), meta: metaParts(s.meta) } : null;
  }, [selected]);

  const pair = useRunPair(
    previous ? runs.get(previous.version) : undefined,
    selected ? runs.get(selected.version) : undefined
  );

  const select = (v: number) => {
    const next = new URLSearchParams(params);
    next.set('v', String(v));
    next.delete('vs');
    setParams(next, { replace: true });
  };

  const restore = async () => {
    if (!selected) return;
    setRestoring(true);
    setRestoreError(null);
    try {
      await updateStrategy(strategyId, {
        dslCode: selected.dslCode,
        changeSummary: `Restore version ${selected.version}`,
      });
      const next = new URLSearchParams(params);
      next.delete('v');
      setParams(next, { replace: true });
      reload();
    } catch {
      setRestoreError('The version wasn’t restored. Please try again.');
    } finally {
      setRestoring(false);
    }
  };

  if (state.status === 'error') {
    return (
      <PanelError
        title="Versions couldn’t be loaded"
        unaffected="The strategy isn’t affected."
        onRetry={reload}
      />
    );
  }
  if (state.status === 'loading') {
    return (
      <div className="panel">
        <SkeletonRows rows={4} cols={2} />
      </div>
    );
  }
  if (!selected) {
    return <EmptyState title="No saved versions" body="Save the strategy to start its history." />;
  }

  const latest = versions[0]?.version;
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="m-0 text-[12.5px] text-fg-3">
          {sessionVersion ? `Version ${sessionVersion} runs in paper. ` : ''}Sessions keep the
          version they started with.
        </p>
        <div className="flex flex-wrap gap-2">
          <Segmented label="Show the change as" options={VIEWS} value={view} onChange={setView} />
          {selected.version !== latest && (
            <button
              type="button"
              onClick={restore}
              disabled={restoring}
              className="btn btn-secondary"
            >
              {restoring ? 'Restoring' : `Restore version ${selected.version}`}
            </button>
          )}
        </div>
      </div>
      {restoreError && <p className="m-0 text-[12.5px] text-risk">{restoreError}</p>}

      <div className="grid items-start gap-7 lg:grid-cols-[320px_minmax(0,1fr)]">
        <ol
          aria-label={`${strategyName} versions`}
          className="panel m-0 list-none overflow-hidden p-0"
        >
          {draft && (
            <li>
              <Link
                to={`/strategies/${strategyId}/edit`}
                className="grid grid-cols-[18px_minmax(0,1fr)] gap-3 border-b border-line px-3.5 py-3 hover:bg-sunk/60"
              >
                <i className="mt-1 block h-[11px] w-[11px] rounded-full border-[1.5px] border-dashed border-fg-3" />
                <span>
                  <b className="text-[13px] font-semibold">Version {draft.version}</b>
                  <span className="mt-0.5 block text-[11.5px] text-fg-3">
                    Draft, unsaved · open in the editor
                  </span>
                </span>
              </Link>
            </li>
          )}
          {versions.map((v) => {
            const on = v.version === selected.version;
            const run = runs.get(v.version);
            const runReturn = run?.results?.metrics ? num(run.results.metrics.totalReturn) : null;
            const running = v.version === sessionVersion;
            const when = toDate(v.createdAt);
            return (
              <li key={v.version}>
                <button
                  type="button"
                  onClick={() => select(v.version)}
                  aria-current={on ? 'true' : undefined}
                  className={`grid w-full grid-cols-[18px_minmax(0,1fr)] gap-3 border-b border-line px-3.5 py-3 text-left last:border-b-0 ${
                    on
                      ? 'bg-accent-soft shadow-[inset_2px_0_0_rgb(var(--accent))]'
                      : 'hover:bg-sunk/60'
                  }`}
                >
                  <i
                    className={`mt-1 block h-[11px] w-[11px] rounded-full ${
                      running ? 'bg-fg' : 'shadow-[inset_0_0_0_1.5px_rgb(var(--fg-3))]'
                    }`}
                  />
                  <span className="min-w-0">
                    <span className="flex items-baseline justify-between gap-2">
                      <b className="text-[13px] font-semibold">Version {v.version}</b>
                      {runReturn !== null ? (
                        <Pct value={runReturn} pnl dp={1} className="text-[12px]" />
                      ) : (
                        run && <span className="text-[11.5px] text-fg-3">backtested</span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-[12px] text-fg-2">
                      {v.changeSummary || (v.version === 1 ? 'First version' : 'No note')}
                    </span>
                    <span className="mt-1 block text-[11.5px] text-fg-3">
                      {when ? dayMonthYear(when) : ''}
                      {running ? ' · paper session' : ''}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>

        <div className="min-w-0">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <b className="text-[15px] font-semibold">
              {previous
                ? `What changed in version ${selected.version}`
                : `Version ${selected.version}`}
            </b>
            {previous ? (
              <label className="flex items-center gap-2 text-[12px] text-fg-3">
                compared with
                <select
                  className="select h-7 py-0 text-[12px]"
                  value={previous.version}
                  onChange={(e) => {
                    const next = new URLSearchParams(params);
                    next.set('vs', e.target.value);
                    setParams(next, { replace: true });
                  }}
                >
                  {versions
                    .filter((v) => v.version !== selected.version)
                    .map((v) => (
                      <option key={v.version} value={v.version}>
                        version {v.version}
                      </option>
                    ))}
                </select>
              </label>
            ) : (
              <span className="text-[12px] text-fg-3">the first version</span>
            )}
          </div>
          {view === 'code' ? (
            <CodeDiff before={previous?.dslCode ?? ''} after={selected.dslCode} />
          ) : diff ? (
            <>
              <p className="m-0 mb-4 text-[13.5px] text-fg-2">
                <Parts parts={diff.meta} />
              </p>
              <Outline lines={diff.lines} label={`Changes in version ${selected.version}`} />
              {diff.changes.length === 0 && (
                <p className="m-0 mt-3 text-[13px] text-fg-2">
                  The definition is the same as version {previous?.version}.
                </p>
              )}
            </>
          ) : firstOutline ? (
            <>
              <p className="m-0 mb-4 text-[13.5px] text-fg-2">
                <Parts parts={firstOutline.meta} />
              </p>
              <Outline lines={firstOutline.lines} label={`Version ${selected.version}`} />
            </>
          ) : (
            <p className="m-0 text-[13px] text-fg-2">
              This version can’t be shown as an outline. The code view shows it.
            </p>
          )}
          {pair && <ResultChange before={pair[0]} after={pair[1]} strategyId={strategyId} />}
        </div>
      </div>
    </div>
  );
}
