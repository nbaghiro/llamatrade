import { useMemo, useState } from 'react';

import { backtestsFor, STRATEGIES, stateLabel, type Strategy } from '../data';

import { useAsk } from './askContext';
import {
  activeSession,
  FUND_NAME,
  lastBacktest,
  PROPOSALS,
  pts,
  strategySpark,
  tone,
} from './model';
import { OutlineView } from './outline';
import { diffItems, itemsOf, type Item } from './outlineModel';
import {
  Button,
  LeftHead,
  LinkButton,
  ListLabel,
  Mono,
  PanelFoot,
  PanelHead,
  PickRow,
  Spark,
  StageCard,
} from './ui';

function withEdits(items: Item[], edits: Record<string, number>): Item[] {
  return items.map((it) =>
    edits[it.id] !== undefined
      ? { ...it, pct: edits[it.id], weight: `${edits[it.id]}%`, mark: 'add' }
      : it
  );
}

/** The selected strategy's outline tree on the stage, with Copilot's edit as + and − rows. */
export function BuilderPanel({ s }: { s: Strategy }) {
  const { proposals, setProposal, ask } = useAsk();
  const prop = PROPOSALS[s.id];
  const state = prop ? (proposals[s.id] ?? 'open') : 'dismissed';
  const [selected, setSelected] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, number>>({});
  const base = useMemo(
    () => itemsOf(s.name, s.cadence, state === 'applied' && prop ? prop.rules : s.rules),
    [s, state, prop]
  );
  const items = useMemo(() => {
    if (state === 'open' && prop) return diffItems(base, itemsOf(s.name, s.cadence, prop.rules));
    return withEdits(base, edits);
  }, [base, state, prop, s, edits]);
  const sel = items.find((i) => i.id === selected);
  const dirty = Object.keys(edits).length > 0 || state === 'applied';
  const version = s.version + 1;
  const ses = activeSession(s.id);
  const b = lastBacktest(s.id);

  return (
    <StageCard>
      <PanelHead
        eyebrow={`Strategy · ${stateLabel(s)}`}
        title={s.name}
        meta={
          state === 'applied'
            ? `Version ${version}, not saved yet · rebalances ${s.cadence}`
            : `Version ${s.version} · ${s.versions[0]?.note ?? 'not saved yet'} · rebalances ${s.cadence}`
        }
        right={
          <>
            {(!prop || state === 'dismissed') && (
              <Button onClick={() => ask(`Suggest a safer edit to ${s.name}`, s.id)}>
                Ask for an edit
              </Button>
            )}
            <Button variant="primary" disabled={!dirty} className="disabled:opacity-40">
              Save as v{version}
            </Button>
          </>
        }
      />
      <div className="-mx-5 mt-[18px] border-y border-line md:-mx-7 md:px-2">
        <OutlineView strategy={s} items={items} selected={selected} onSelect={setSelected} />
      </div>
      {state === 'open' && prop ? (
        <div className="-mx-5 flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line bg-sunk/50 px-5 py-3 md:-mx-7 md:px-7">
          <Mono className="text-fg">Copilot</Mono>
          <span className="text-[13px] text-fg">{prop.note}</span>
          <span className="font-mono text-[11.5px] tabular-nums text-fg-3">
            v{prop.version}{' '}
            <span className={tone(prop.effect.ret)}>{pts(prop.effect.ret * 100)}</span> · worst{' '}
            {pts(prop.effect.worst * 100)}
          </span>
          <span className="ml-auto flex gap-2">
            <Button variant="primary" onClick={() => setProposal(s.id, 'applied')}>
              Apply
            </Button>
            <Button onClick={() => setProposal(s.id, 'dismissed')}>Discard</Button>
          </span>
        </div>
      ) : (
        <div className="-mx-5 flex min-h-[50px] flex-wrap items-center gap-3 border-b border-line px-5 py-2 text-[12.5px] text-fg-3 md:-mx-7 md:px-7">
          {sel?.kind === 'asset' && sel.symbol && !sel.pick ? (
            <>
              <Mono className="text-fg-2">Asset</Mono>
              <span className="text-fg">
                {sel.symbol} · {FUND_NAME[sel.symbol]}
              </span>
              <span className="ml-auto inline-flex items-center gap-2">
                <Button
                  aria-label="Lower weight"
                  onClick={() =>
                    setEdits((e) => ({ ...e, [sel.id]: Math.max(0, (sel.pct ?? 0) - 5) }))
                  }
                >
                  −
                </Button>
                <span className="w-11 text-center font-mono text-[13px] tabular-nums text-fg">
                  {sel.pct}%
                </span>
                <Button
                  aria-label="Raise weight"
                  onClick={() =>
                    setEdits((e) => ({ ...e, [sel.id]: Math.min(100, (sel.pct ?? 0) + 5) }))
                  }
                >
                  +
                </Button>
                {Object.keys(edits).length > 0 && (
                  <Button variant="quiet" onClick={() => setEdits({})}>
                    Undo
                  </Button>
                )}
              </span>
            </>
          ) : (
            <span>Select an asset row to change its weight. The caret folds a branch.</span>
          )}
        </div>
      )}
      <PanelFoot
        flush
        note={
          b ? (
            <span className="font-mono tabular-nums">
              Last backtest v{b.version} <span className={tone(b.ret)}>{pts(b.ret * 100)}</span> ·
              SPY {pts(b.spy * 100)} · worst {pts(b.worst * 100)}
            </span>
          ) : (
            'Not backtested yet.'
          )
        }
      >
        <LinkButton to={b ? `/k/backtests/${b.id}` : '/k/backtests'}>Backtest</LinkButton>
        {ses ? (
          <LinkButton to={`/k/sessions/${ses.id}`}>Open session</LinkButton>
        ) : (
          <Button>Start session</Button>
        )}
      </PanelFoot>
    </StageCard>
  );
}

export function StrategiesLeft({ sel }: { sel: string }) {
  const { ask, proposals } = useAsk();
  const groups: [string, Strategy[]][] = [
    ['Running', STRATEGIES.filter((s) => s.state === 'running')],
    ['Not running', STRATEGIES.filter((s) => s.state === 'stopped' || s.state === 'never-run')],
    ['Drafts', STRATEGIES.filter((s) => s.state === 'draft')],
  ];
  return (
    <>
      <LeftHead
        title="Strategies"
        sub="3 running, 3 not running and 1 draft."
        right={
          <Button variant="primary" onClick={() => ask('Draft a trend strategy on QQQ')}>
            New
          </Button>
        }
      />
      {groups.map(([label, rows]) =>
        rows.length ? (
          <div key={label}>
            <ListLabel right={label === 'Running' ? <span>Backtest</span> : undefined}>
              {label}
            </ListLabel>
            {rows.map((s) => {
              const spark = strategySpark(s);
              const b = backtestsFor(s.id)[0];
              const pending = PROPOSALS[s.id] && (proposals[s.id] ?? 'open') === 'open';
              return (
                <PickRow
                  key={s.id}
                  to={`/k/strategies/${s.id}`}
                  on={sel === s.id}
                  title={
                    <span className="inline-flex items-center gap-2">
                      {s.name}
                      {pending && (
                        <span className="rounded-[4px] border border-line-strong px-1 font-mono text-[9.5px] uppercase leading-[15px] tracking-[0.08em] text-fg-2">
                          Edit
                        </span>
                      )}
                    </span>
                  }
                  sub={`v${s.version} · ${s.state === 'running' ? `on ${s.mode}` : stateLabel(s).toLowerCase()} · ${s.cadence}`}
                  right={
                    spark ? (
                      <>
                        <Spark values={spark} width={52} height={20} />
                        <span
                          className={`w-[50px] text-right font-mono text-[12.5px] tabular-nums ${b ? tone(b.ret) : 'text-fg-3'}`}
                        >
                          {b ? pts(b.ret * 100) : ''}
                        </span>
                      </>
                    ) : (
                      <span className="text-[12px] text-fg-3">No runs</span>
                    )
                  }
                />
              );
            })}
          </div>
        ) : null
      )}
    </>
  );
}
