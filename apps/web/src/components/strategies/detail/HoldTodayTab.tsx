import { num, toDate } from '@llamatrade/core/format';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import type { IfBlock } from '@llamatrade/core/strategy/types';
import { useMemo } from 'react';

import { formatMoney } from '../../../lib/format';
import { buildOutline, holdingsWhen } from '../../../lib/outline';
import { nextRebalanceDate } from '../../../lib/sessionState';
import { dayLabel, etToday } from '../../sessions/sessionRows';
import type { RunningSession } from '../../strategy-builder/hooks/useRunningSession';
import { Outline } from '../../strategy-builder/outline/Outline';
import { sessionHoldings } from '../../strategy-builder/rail/sessionHoldings';
import { Money } from '../../ui';
import { holdingWords, holdSentences, listWords } from '../holdSentences';
import { readableIfs, readingText, todaysChoices, type Reading } from '../rules/evaluate';
import { operandWords } from '../rules/ruleSentence';
import type { RulesModel } from '../rules/useRulesModel';

import { holdGap } from './holdGap';
import { Panel } from './OverviewTab';
import { FactRow } from './RulesTab';
import type { StrategySession } from './useStrategySession';

const COMPARE_WORD = (r: Reading) =>
  r.value > r.against ? 'above' : r.value < r.against ? 'below' : 'at';

const read1 = readingText;

/** "TLT 60% and GLD 40%" with each holding in bold mono. */
function Holdings({
  holdings,
  rankedBy,
}: Pick<ReturnType<typeof holdingsWhen>, 'holdings' | 'rankedBy'>) {
  if (holdings.some((h) => h.pct === null)) {
    return (
      <b className="font-mono font-semibold text-fg">{holdingWords({ holdings, rankedBy })}</b>
    );
  }
  return (
    <>
      {holdings.map((h, i) => (
        <span key={h.symbol}>
          {i > 0 && (i === holdings.length - 1 ? ' and ' : ', ')}
          <b className="font-mono font-semibold text-fg">
            {h.symbol} {Math.round((h.pct ?? 0) * 10) / 10}%
          </b>
        </span>
      ))}
    </>
  );
}

/** Where today's reading sits on the indicator's range, with the line and the last switch. */
function Scale({
  block,
  reading,
  lastSwitch,
  history,
}: {
  block: IfBlock;
  reading: Reading;
  lastSwitch: { at: Date; value: number } | null;
  history: readonly number[];
}) {
  const left = block.condition.left;
  const bounded = left.type === 'indicator' && left.indicator === 'rsi';
  const finite = history.filter(Number.isFinite);
  const lo = bounded ? 0 : Math.min(...finite, reading.against);
  const hi = bounded ? 100 : Math.max(...finite, reading.against);
  const at = (v: number) => `${Math.min(100, Math.max(0, ((v - lo) / (hi - lo || 1)) * 100))}%`;
  return (
    <div className="relative mx-1 mb-1 mt-8 h-11">
      <div className="absolute inset-x-0 top-[9px] h-2 rounded-full bg-sunk" />
      <div
        className="absolute top-0 h-[26px] w-px bg-fg"
        style={{ left: at(reading.against) }}
        aria-hidden="true"
      />
      <span
        className="absolute -top-5 -translate-x-1/2 font-mono text-[11px] text-fg-2"
        style={{ left: at(reading.against) }}
      >
        {read1(reading.against)}
      </span>
      <span
        className="absolute top-[5px] h-4 w-4 -translate-x-1/2 rounded-full bg-accent"
        style={{ left: at(reading.value) }}
        aria-hidden="true"
      />
      <span
        className="absolute top-7 -translate-x-1/2 whitespace-nowrap font-mono text-[11px] font-semibold text-accent"
        style={{ left: at(reading.value) }}
      >
        {read1(reading.value)} now
      </span>
      {lastSwitch && (
        <span
          className="absolute top-7 whitespace-nowrap pl-14 font-mono text-[11px] text-fg-3 max-md:hidden"
          style={{ left: at(reading.value) }}
        >
          {read1(lastSwitch.value)} on {dayLabel(lastSwitch.at)}
        </span>
      )}
      <span className="absolute left-0 top-7 font-mono text-[11px] text-fg-3">{read1(lo)}</span>
      <span className="absolute right-0 top-7 font-mono text-[11px] text-fg-3">{read1(hi)}</span>
    </div>
  );
}

/** Would hold today (holdings2 A): the rules evaluated on today's closes, said in a sentence. */
export function HoldTodayTab({
  strategy,
  ss,
  running,
  model,
}: {
  strategy: Strategy;
  ss: StrategySession;
  running: RunningSession;
  model: RulesModel;
}) {
  const { tree, readings } = model;
  const held = useMemo(() => sessionHoldings(running.positions), [running.positions]);
  const values = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of running.positions) {
      m.set(p.symbol, (m.get(p.symbol) ?? 0) + Math.abs(num(p.marketValue)));
    }
    return m;
  }, [running.positions]);
  const lines = useMemo(() => (tree ? buildOutline(tree) : []), [tree]);

  const row = ss.row;
  const next = nextRebalanceDate(row?.rebalance || strategy.rebalance, etToday());

  if (!tree) {
    return (
      <div className="panel px-5 py-4 text-[13px] text-fg-2">
        The rules can’t be read, so this page can’t work out what they would hold. The Rules tab
        shows the code.
      </div>
    );
  }

  const ifs = readableIfs(tree);
  const allIfs = Object.values(tree.blocks).filter((b) => b.type === 'if');
  const ready = readings.status === 'ready' ? readings.byBlock : null;
  const today = ready ? new Map([...ready].map(([id, r]) => [id, r.today])) : new Map();
  const choices = allIfs.length === 0 ? new Map<string, boolean>() : todaysChoices(tree, today);
  const would = choices ? holdingsWhen(tree, choices) : null;
  const single = allIfs.length === 1 && ifs.length === 1 ? ifs[0] : null;
  const singleReading = single && ready ? ready.get(single.id) : undefined;
  const otherSide =
    single && choices
      ? holdingsWhen(tree, new Map([[single.id, !(choices.get(single.id) ?? true)]]))
      : null;
  const asOf = singleReading?.today?.asOf ?? null;
  const sleeve = row?.figures.equity ?? null;
  const gap = would && sleeve !== null ? holdGap(would.holdings, values, sleeve) : null;
  const sameSide =
    would && held.holdings.length > 0
      ? held.holdings.every((h) => would.holdings.some((w) => w.symbol === h.symbol))
      : null;

  if (!would) {
    const sentences = holdSentences(tree);
    return (
      <div className="grid gap-5">
        <p className="m-0 max-w-[920px] text-[15px] leading-[1.6] text-fg-2">
          {readings.status === 'loading'
            ? 'Reading today’s closes…'
            : readings.status === 'error'
              ? 'Today’s prices didn’t load, so this page can’t say which side the rules pick.'
              : `This strategy has ${allIfs.length} conditions and some of them read data this page can’t compute, so the session works out the side at its rebalance${next ? ` on ${dayLabel(next)}` : ''}.`}
        </p>
        <FactRow
          items={sentences.slice(0, 4).map((s, i) => ({
            label:
              s.when === null
                ? 'As written'
                : s.when === 'Otherwise'
                  ? 'Otherwise'
                  : `Branch ${i + 1}`,
            value: holdingWords(s.scenario),
            sub: s.when ?? undefined,
          }))}
        />
        <Panel title="The rules that decide it">
          <Outline lines={lines} dense label={`${strategy.name} outline`} />
        </Panel>
      </div>
    );
  }

  const reason =
    single && singleReading?.today ? (
      <>
        , because {operandWords(single.condition.left).replace(/ \d+-day /, ' ')} is{' '}
        <b className="font-mono font-semibold text-fg">{read1(singleReading.today.value)}</b>,{' '}
        {COMPARE_WORD(singleReading.today)}{' '}
        <b className="font-mono font-semibold text-fg">{read1(singleReading.today.against)}</b>
      </>
    ) : ready && ready.size > 0 ? (
      <>
        , because{' '}
        {listWords(
          [...ready].flatMap(([id, r]) => {
            const b = tree.blocks[id];
            return b?.type === 'if' && r.today
              ? [`${operandWords(b.condition.left)} is ${read1(r.today.value)}`]
              : [];
          })
        )}
      </>
    ) : null;

  const gapCell = (v: number | null) => (v === null ? '·' : `${v.toFixed(1)}%`);

  return (
    <div className="grid gap-5">
      <div className="grid gap-1.5">
        <p className="m-0 max-w-[1000px] text-[21px] leading-[1.45] tracking-[-0.01em] text-fg-2 md:text-[26px]">
          It would hold <Holdings {...would} />
          {reason}.
        </p>
        <span className="text-[12px] text-fg-3">
          {asOf ? `With daily closes to ${dayLabel(etToday(asOf))}` : 'From the rules as written'}
          {would.holdings.some((h) => h.pct === null) &&
            '. The ranking that picks the funds runs at the rebalance, so their weights aren’t known here.'}
        </span>
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
        {single && singleReading?.today ? (
          <section className="panel min-w-0">
            <header className="flex items-baseline justify-between gap-3 border-b border-line px-5 py-3.5">
              <h3 className="m-0 text-[13.5px] font-semibold">
                {operandWords(single.condition.left)}
              </h3>
              {single.condition.left.type === 'indicator' &&
                single.condition.left.indicator === 'rsi' && (
                  <span className="text-[12px] text-fg-3">0 to 100</span>
                )}
            </header>
            <div className="px-5 pb-4 pt-3">
              <Scale
                block={single}
                reading={singleReading.today}
                lastSwitch={singleReading.rebalances.lastSwitch}
                history={singleReading.history.left.slice(-504)}
              />
              {otherSide && (
                <div className="mt-3 flex flex-wrap items-baseline justify-between gap-2 text-[12.5px] text-fg-2">
                  <span>
                    {singleReading.today.holds ? 'Otherwise' : 'When the rule holds'} it would hold
                  </span>
                  <span className="font-mono text-fg">{holdingWords(otherSide)}</span>
                </div>
              )}
            </div>
          </section>
        ) : (
          <Panel title="The rules that decide it">
            <Outline lines={lines} dense label={`${strategy.name} outline`} />
          </Panel>
        )}

        {row && gap && gap.rows.length > 0 ? (
          <section className="panel min-w-0 overflow-x-auto">
            <header className="flex items-baseline justify-between gap-3 border-b border-line px-5 py-3.5">
              <h3 className="m-0 text-[13.5px] font-semibold">Against the session</h3>
              {held.asOf && (
                <span className="text-[12px] text-fg-3">{dayLabel(etToday(held.asOf))}</span>
              )}
            </header>
            <table className="w-full border-collapse text-[12.5px]">
              <thead>
                <tr className="text-left">
                  <th className="px-5 py-2 font-medium">
                    <span className="kicker">Symbol</span>
                  </th>
                  <th className="px-3 py-2 text-right font-medium">
                    <span className="kicker">Would hold</span>
                  </th>
                  <th className="px-3 py-2 text-right font-medium">
                    <span className="kicker">Holds</span>
                  </th>
                  <th className="px-5 py-2 text-right font-medium max-md:hidden">
                    <span className="kicker">Gap</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {gap.rows.map((r) => (
                  <tr key={r.symbol} className="border-t border-line">
                    <td
                      className={`px-5 py-2.5 font-mono ${r.symbol === 'Cash' ? 'text-fg-2' : 'font-semibold'}`}
                    >
                      {r.symbol}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono">{gapCell(r.would)}</td>
                    <td className="px-3 py-2.5 text-right font-mono">{r.holds.toFixed(1)}%</td>
                    <td className="px-5 py-2.5 text-right font-mono text-fg-2 max-md:hidden">
                      {r.gap === null ? '·' : formatMoney(r.gap, { dp: 0 })}
                    </td>
                  </tr>
                ))}
                {sleeve !== null && (
                  <tr className="border-t border-line">
                    <td className="px-5 py-2.5 font-semibold">Sleeve</td>
                    <td colSpan={2} className="px-3 py-2.5 text-right font-mono font-semibold">
                      <Money value={sleeve} />
                    </td>
                    <td className="max-md:hidden" />
                  </tr>
                )}
              </tbody>
            </table>
          </section>
        ) : (
          <Panel title="Against the session">
            <p className="m-0 text-[12.5px] text-fg-2">
              {row
                ? 'The session holds no positions right now.'
                : 'No session runs this strategy yet, so there is nothing to compare with.'}
            </p>
          </Panel>
        )}
      </div>

      {row && (
        <FactRow
          items={[
            {
              label: 'Version',
              value: String(running.version ?? row.version ?? strategy.version),
              sub: row.startedAt
                ? `in the session since ${dayLabel(etToday(toDate(row.session.startedAt) ?? row.startedAt))}`
                : undefined,
            },
            {
              label: 'Same side as the session',
              value: sameSide === null ? '·' : sameSide ? 'Yes' : 'No',
              sub: held.holdings.map((h) => h.symbol).join(' and ') || undefined,
            },
            {
              label: 'Largest gap',
              value: gap?.largest
                ? `${Math.abs((gap.largest.would ?? 0) - gap.largest.holds).toFixed(1)} pts`
                : '·',
              sub: gap?.largest ? gap.largest.symbol : undefined,
            },
            {
              label: 'Next rebalance',
              value: next
                ? next.getTime() === etToday().getTime()
                  ? 'Today'
                  : dayLabel(next)
                : 'Each day',
              sub: row.rebalance || strategy.rebalance || undefined,
            },
          ]}
        />
      )}
    </div>
  );
}
