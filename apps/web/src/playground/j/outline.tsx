import { useMemo, useState, type ReactNode } from 'react';

import { LiveMarker, Ticker, TreeBar, TreeRow } from '../../components/ui/TreeRow';
import { collapse, guidesOf, withKids } from '../../lib/outlineTree';
import type { Strategy, Value } from '../data';

import { activeSession, FUND_NAME } from './model';
import { liveSet, type Item, type Kind } from './outlineModel';

export function Phrase({ parts }: { parts: (string | Value)[] }) {
  return (
    <>
      {parts.map((p, i) =>
        typeof p === 'string' ? (
          <span key={i}>{i ? ` ${p}` : p}</span>
        ) : p.kind === 'symbol' ? (
          <span key={i}>
            {' '}
            <Ticker symbol={p.text} />
          </span>
        ) : (
          <span key={i}>
            {' '}
            <b
              className={`font-medium ${p.kind === 'number' ? 'font-mono text-[0.93em] underline decoration-line-strong decoration-dotted underline-offset-4' : ''}`}
            >
              {p.text}
            </b>
          </span>
        )
      )}
    </>
  );
}

const TYPE: Record<Kind, string> = {
  strategy: 'Strategy',
  if: 'If',
  else: 'Else',
  filter: 'Filter',
  weight: 'Weight',
  group: 'Group',
  asset: 'Asset',
};

export function OutlineView({
  strategy,
  items,
  compact = false,
  selected,
  onSelect,
  end,
}: {
  strategy: Strategy;
  items: Item[];
  compact?: boolean;
  selected?: string | null;
  onSelect?: (id: string) => void;
  end?: (it: Item) => ReactNode;
}) {
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const session = activeSession(strategy.id);
  const held = useMemo(() => new Set(session?.holds.map((h) => h.symbol) ?? []), [session]);
  const live = useMemo(() => liveSet(items, held), [items, held]);
  const markerAt = useMemo(() => {
    const decision = items.find(
      (it) => live.has(it.id) && (it.kind === 'if' || it.kind === 'else' || it.kind === 'filter')
    );
    return decision?.id ?? items.find((it) => it.depth === 1 && live.has(it.id))?.id;
  }, [items, live]);
  const rows = useMemo(() => {
    const flat = withKids(items.map((it) => ({ ...it, live: live.has(it.id) })));
    const shown = collapse(flat, closed);
    const gs = guidesOf(shown);
    return shown.map((r, i) => ({ r, g: gs[i] }));
  }, [items, live, closed]);
  const toggle = (id: string) =>
    setClosed((c) => {
      const n = new Set(c);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const holdPct = (sym?: string) => session?.holds.find((h) => h.symbol === sym)?.weight;

  return (
    <div role="tree" aria-label={`${strategy.name} outline`} className="py-1">
      {rows.map(({ r, g }) => {
        const isLive = live.has(r.id);
        const held = r.kind === 'asset' ? holdPct(r.symbol) : undefined;
        return (
          <TreeRow
            key={r.id}
            guides={g}
            type={TYPE[r.kind]}
            closed={r.kids ? closed.has(r.id) : undefined}
            onToggle={() => toggle(r.id)}
            hiddenCount={r.hidden}
            live={isLive}
            mark={r.mark}
            selected={selected === r.id}
            onClick={() => onSelect?.(r.id)}
            phraseClass={r.kind === 'strategy' ? 'font-semibold' : ''}
            typeWidth={compact ? 64 : 72}
            end={
              end?.(r) ??
              (r.kind === 'asset' ? (
                <>
                  {held !== undefined && !compact && (
                    <span className="hidden font-mono tabular-nums text-fg-3 md:inline">
                      holds {held.toFixed(1)}%
                    </span>
                  )}
                  <span className="hidden sm:block">
                    <TreeBar
                      pct={r.pct}
                      pick={r.pick}
                      live={isLive}
                      muted={r.mark === 'del'}
                      width={compact ? 72 : 120}
                    />
                  </span>
                  <span className="w-[44px] text-right sm:w-[68px] font-mono tabular-nums text-fg-2">
                    {r.pick ? 'if picked' : r.weight}
                  </span>
                </>
              ) : r.id === markerAt ? (
                <LiveMarker />
              ) : undefined)
            }
          >
            {r.kind === 'asset' && r.symbol ? (
              <>
                <Ticker symbol={r.symbol} on={isLive && r.mark !== 'del'} />
                <span className="ml-2 text-fg-3">{FUND_NAME[r.symbol] ?? ''}</span>
              </>
            ) : r.kind === 'strategy' ? (
              <>
                {strategy.name}
                <span className="ml-2 font-normal text-fg-3">rebalance {strategy.cadence}</span>
              </>
            ) : (
              <Phrase parts={r.parts} />
            )}
          </TreeRow>
        );
      })}
    </div>
  );
}
