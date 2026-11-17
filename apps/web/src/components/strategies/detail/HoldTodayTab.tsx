import { num } from '@llamatrade/core/format';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { fromDSLString } from '@llamatrade/core/strategy/serializer';
import { useMemo } from 'react';

import { etClock } from '../../../lib/marketClock';
import { buildOutline } from '../../../lib/outline';
import { nextRebalanceDate } from '../../../lib/sessionState';
import { dayLabel, etToday } from '../../sessions/sessionRows';
import type { RunningSession } from '../../strategy-builder/hooks/useRunningSession';
import { Outline } from '../../strategy-builder/outline/Outline';
import { sessionHoldings } from '../../strategy-builder/rail/sessionHoldings';
import { Money } from '../../ui';
import { holdingWords, holdSentences, listWords } from '../holdSentences';

import { Panel } from './OverviewTab';
import type { StrategySession } from './useStrategySession';

/** Two branches can be compared side by side; more fall back to the outline. */
const MAX_COLUMNS = 2;

/** Would hold today, said in sentences (holdings2 A), from the rules as written. */
export function HoldTodayTab({
  strategy,
  ss,
  running,
}: {
  strategy: Strategy;
  ss: StrategySession;
  running: RunningSession;
}) {
  const parsed = useMemo(() => fromDSLString(strategy.dslCode), [strategy.dslCode]);
  const sentences = useMemo(() => (parsed ? holdSentences(parsed.tree) : []), [parsed]);
  const lines = useMemo(() => (parsed ? buildOutline(parsed.tree) : []), [parsed]);
  const held = useMemo(() => sessionHoldings(running.positions), [running.positions]);
  const values = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of running.positions) {
      m.set(p.symbol, (m.get(p.symbol) ?? 0) + Math.abs(num(p.marketValue)));
    }
    return m;
  }, [running.positions]);

  const row = ss.row;
  const next =
    row && row.state === 'running'
      ? nextRebalanceDate(row.rebalance || strategy.rebalance, etToday())
      : null;

  if (!parsed || sentences.length === 0) {
    return (
      <div className="panel px-5 py-4 text-[13px] text-fg-2">
        The rules can’t be read as an outline, so they can’t be put in sentences here. The Rules tab
        shows the code.
      </div>
    );
  }

  const columns = sentences.length <= MAX_COLUMNS ? sentences : [];
  const symbols = [
    ...new Set([
      ...sentences.flatMap((s) => s.scenario.holdings.map((h) => h.symbol)),
      ...held.holdings.map((h) => h.symbol),
    ]),
  ];
  const cell = (pct: number | null | undefined) =>
    pct === undefined ? '·' : pct === null ? 'ranked' : `${pct.toFixed(1)}%`;

  return (
    <div className="grid gap-6">
      <div className="grid max-w-[960px] gap-3">
        <span className="kicker">As written</span>
        <p className="m-0 text-[20px] leading-[1.5] tracking-[-0.01em] text-fg md:text-[24px]">
          {sentences.map((s, i) => (
            <span key={i}>
              {i > 0 && ' '}
              {s.when === null
                ? `${strategy.name} holds `
                : s.when === 'Otherwise'
                  ? 'Otherwise it holds '
                  : `${s.when}, ${i === 0 ? strategy.name : 'it'} holds `}
              <b className="font-mono font-semibold">{holdingWords(s.scenario)}</b>.
            </span>
          ))}
        </p>
        <p className="m-0 text-[15px] leading-[1.6] text-fg-2">
          {row && held.holdings.length > 0 ? (
            <>
              The {row.session.mode === ExecutionMode.LIVE ? 'live' : 'paper'} session
              {running.version ? ` runs version ${running.version} and` : ''} holds{' '}
              <b className="font-mono text-fg">
                {listWords(held.holdings.map((h) => `${h.symbol} ${h.pct.toFixed(1)}%`))}
              </b>
              {held.asOf ? ` as of ${etClock(held.asOf)}` : ''}.{' '}
            </>
          ) : row ? (
            'The session holds no positions right now. '
          ) : (
            'No session runs this strategy yet. '
          )}
          Which side the rules pick today depends on today’s indicator values, which this page
          doesn’t read yet
          {next ? `; the session works it out at its next rebalance on ${dayLabel(next)}.` : '.'}
        </p>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {columns.length > 0 && (
          <section className="panel overflow-x-auto">
            <table className="w-full min-w-[420px] border-collapse text-[12.5px]">
              <thead>
                <tr className="text-left text-fg-3">
                  <th className="px-4 py-2.5 font-medium">
                    <span className="kicker">Symbol</span>
                  </th>
                  {columns.map((c, i) => (
                    <th key={i} className="px-4 py-2.5 text-right font-medium">
                      <span className="kicker">
                        {c.when === null
                          ? 'As written'
                          : c.when === 'Otherwise'
                            ? 'Otherwise'
                            : 'When it holds'}
                      </span>
                    </th>
                  ))}
                  {row && (
                    <>
                      <th className="px-4 py-2.5 text-right font-medium">
                        <span className="kicker">Holds</span>
                      </th>
                      <th className="px-4 py-2.5 text-right font-medium">
                        <span className="kicker">Value</span>
                      </th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {symbols.map((sym) => {
                  const h = held.holdings.find((x) => x.symbol === sym);
                  return (
                    <tr key={sym} className="border-t border-line">
                      <td className="px-4 py-2.5 font-mono font-semibold">{sym}</td>
                      {columns.map((c, i) => (
                        <td key={i} className="px-4 py-2.5 text-right font-mono text-fg-2">
                          {cell(c.scenario.holdings.find((x) => x.symbol === sym)?.pct)}
                        </td>
                      ))}
                      {row && (
                        <>
                          <td className="px-4 py-2.5 text-right font-mono">
                            {h ? `${h.pct.toFixed(1)}%` : '·'}
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono text-fg-2">
                            {values.get(sym) ? <Money value={values.get(sym) ?? 0} dp={0} /> : '·'}
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        )}
        <Panel title="The rules that decide it">
          <Outline lines={lines} dense label={`${strategy.name} outline`} />
        </Panel>
      </div>
    </div>
  );
}
