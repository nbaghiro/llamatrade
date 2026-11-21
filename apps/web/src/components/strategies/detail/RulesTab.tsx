import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { lazy, Suspense, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';

import {
  buildOutline,
  longestLookback,
  metaParts,
  rebalanceWord,
  strategySymbols,
} from '../../../lib/outline';
import { nextRebalanceDate } from '../../../lib/sessionState';
import { dayLabel, etToday } from '../../sessions/sessionRows';
import { Outline, Parts } from '../../strategy-builder/outline/Outline';
import { Segmented, Skeleton } from '../../ui';
import type { SentenceTerm } from '../rules/ruleSentence';
import { RuleSentenceView } from '../rules/RuleSentenceView';
import { TermPanel } from '../rules/TermPanel';
import type { RulesModel } from '../rules/useRulesModel';
import { useMediaQuery } from '../useMediaQuery';

const DslCodeBlock = lazy(() => import('../DslCodeBlock'));

type View = 'sentence' | 'outline' | 'code';

const VIEWS = [
  { key: 'sentence', label: 'Sentence' },
  { key: 'outline', label: 'Outline' },
  { key: 'code', label: 'Code' },
] as const;

export function FactRow({
  items,
}: {
  items: ReadonlyArray<{ label: string; value: ReactNode; sub?: ReactNode }>;
}) {
  return (
    <dl
      className={`m-0 grid grid-cols-2 gap-px overflow-hidden rounded-panel border border-line bg-line ${
        items.length === 4 ? 'md:grid-cols-4' : 'md:grid-cols-3'
      }`}
    >
      {items.map((it, i) => (
        <div key={i} className="min-w-0 bg-panel px-4 py-3">
          <dt className="kicker">{it.label}</dt>
          <dd className="m-0 mt-1 truncate font-mono text-[15px] font-medium">{it.value}</dd>
          {it.sub && (
            <div className="mt-0.5 truncate font-mono text-[11.5px] text-fg-3">{it.sub}</div>
          )}
        </div>
      ))}
    </dl>
  );
}

/** A bottom sheet for one term on a phone. */
function TermSheet({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div
      className="fixed inset-0 z-[70] flex items-end"
      style={{ background: 'var(--scrim)' }}
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="max-h-[80vh] w-full overflow-y-auto rounded-t-[18px] border-t border-line-strong bg-panel px-5 pb-8 pt-2 shadow-xl"
      >
        <div className="mx-auto mb-3 h-1 w-9 rounded-full bg-line-strong" />
        {children}
      </div>
    </div>
  );
}

/** Rules (rules2 A): one sentence with every value opening its rule, then Outline and Code. */
export function RulesTab({ strategy, model }: { strategy: Strategy; model: RulesModel }) {
  const { sentence, tree, timeframe, benchmark } = model;
  const wide = useMediaQuery('(min-width: 1024px)');
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<View>(sentence?.outlineFirst ? 'outline' : 'sentence');
  const terms = useMemo(
    () => (sentence?.parts ?? []).filter((p): p is SentenceTerm => p.kind === 'term'),
    [sentence]
  );
  const asked = params.get('term');
  const [openId, setOpenId] = useState<string | null>(asked);
  useEffect(() => {
    if (asked) {
      setOpenId(asked);
      return;
    }
    if (wide && openId === null) {
      const first = terms.find(
        (t) => t.target.kind === 'condition' && t.target.part === 'threshold'
      );
      if (first) setOpenId(first.id);
    }
    // Only on first render and when the link asks for a term.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asked, wide, terms]);
  const open = terms.find((t) => t.id === openId) ?? null;
  const close = () => {
    setOpenId(null);
    if (asked) {
      params.delete('term');
      setParams(params, { replace: true });
    }
  };

  const lines = useMemo(() => (tree ? buildOutline(tree) : []), [tree]);
  const symbols = tree ? strategySymbols(tree, benchmark) : { held: [], signals: [] };
  const signalsOnly = tree ? strategySymbols(tree).signals : [];
  const lookback = tree ? longestLookback(tree) : 0;
  const rebalance = rebalanceWord(timeframe);
  const next = nextRebalanceDate(rebalance, etToday());
  const today = etToday();

  const meta = !sentence
    ? `Version ${strategy.version || 1}`
    : sentence.outlineFirst
      ? `Version ${strategy.version || 1} · ${sentence.ruleCount} rules, so it opens in Outline`
      : `Version ${strategy.version || 1} · written from the rules`;

  const panel = open ? (
    <TermPanel
      key={open.id}
      term={open}
      model={model}
      strategy={strategy}
      onClose={close}
      compact={!wide}
    />
  ) : null;

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-[12px] text-fg-3">{meta}</span>
        <span className="flex items-center gap-2">
          <Segmented label="Rules view" options={VIEWS} value={view} onChange={setView} />
        </span>
      </div>

      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_400px]">
        <section className="grid min-w-0 gap-5">
          {view === 'code' || !tree || !sentence ? (
            <Suspense fallback={<Skeleton className="h-48 w-full" />}>
              <DslCodeBlock code={strategy.dslCode} className="rounded-panel border border-line" />
            </Suspense>
          ) : (
            <>
              <RuleSentenceView
                parts={sentence.parts}
                openId={openId}
                onOpen={(id) => setOpenId((cur) => (cur === id ? null : id))}
                className={`text-fg-2 ${
                  view === 'outline'
                    ? 'text-[20px] leading-[1.6] md:text-[26px]'
                    : 'text-[21px] leading-[1.6] tracking-[-0.01em] md:text-[30px] md:leading-[1.55]'
                }`}
              />
              {view === 'sentence' ? (
                <>
                  <p className="m-0 text-[12.5px] text-fg-3">
                    Each underlined part opens its rule. The sentence is rebuilt from the code
                    whenever you save, so it matches what runs.
                  </p>
                  <FactRow
                    items={[
                      {
                        label: 'Trades',
                        value: `${symbols.held.length} ${symbols.held.length === 1 ? 'symbol' : 'symbols'}`,
                        sub: symbols.held.join(' '),
                      },
                      {
                        label: 'Reads only',
                        value: symbols.signals.length ? symbols.signals.join(' ') : 'Nothing else',
                        sub: !symbols.signals.includes(benchmark)
                          ? 'signals'
                          : signalsOnly.includes(benchmark)
                            ? 'signal and benchmark'
                            : symbols.signals.length === 1
                              ? 'benchmark'
                              : `${benchmark} is the benchmark`,
                      },
                      {
                        label: 'History needed',
                        value: lookback ? `${lookback} days` : 'None',
                        sub: lookback ? 'trading days' : undefined,
                      },
                      {
                        label: 'Next rebalance',
                        value: next
                          ? next.getTime() === today.getTime()
                            ? 'Today'
                            : dayLabel(next)
                          : 'Each day',
                        sub: rebalance,
                      },
                    ]}
                  />
                </>
              ) : (
                <div className="panel px-5 py-4">
                  <p className="m-0 mb-4 text-[13.5px] text-fg-2">
                    <Parts parts={metaParts({ timeframe, benchmark })} />
                  </p>
                  <Outline lines={lines} label={`${strategy.name} outline`} />
                </div>
              )}
            </>
          )}
        </section>
        {wide && panel && view !== 'code' && <aside className="lg:sticky lg:top-4">{panel}</aside>}
      </div>
      {!wide && panel && view !== 'code' && <TermSheet onClose={close}>{panel}</TermSheet>}
    </div>
  );
}
