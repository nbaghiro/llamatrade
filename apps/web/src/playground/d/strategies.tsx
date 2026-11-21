import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { backtestsFor, STRATEGIES, stateLabel, strategyById, type Strategy } from '../data';

import { useAsk } from './askContext';
import { Page, PageHead } from './frame';
import { LedgerHead, StrategyLedger } from './ledger';
import { activeSession, FUND_NAME, PROPOSALS, pts, tone } from './model';
import { OutlineView } from './outline';
import { diffItems, itemsOf, type Item } from './outlineModel';
import { Button, Foot, Label, LinkButton, Mono, SectionHead, Segmented } from './ui';

type Filter = 'all' | 'running' | 'resting' | 'draft';

export function StrategiesList() {
  const { ask } = useAsk();
  const [filter, setFilter] = useState<Filter>('all');
  const rows = STRATEGIES.filter((s) =>
    filter === 'all'
      ? true
      : filter === 'running'
        ? s.state === 'running'
        : filter === 'draft'
          ? s.state === 'draft'
          : s.state === 'stopped' || s.state === 'never-run'
  );
  return (
    <Page placeholder="Ask about your strategies, or describe a new one">
      <PageHead
        eyebrow="Nov 20, 2026 · 12:04 ET"
        title="Strategies"
        meta="3 running · 1 stopped · 2 never run · 1 draft"
        right={
          <>
            <Segmented
              label="Filter"
              value={filter}
              onChange={setFilter}
              options={[
                { key: 'all', label: 'All' },
                { key: 'running', label: 'Running' },
                { key: 'resting', label: 'Not running' },
                { key: 'draft', label: 'Drafts' },
              ]}
            />
            <Button variant="primary" onClick={() => ask('Draft a trend strategy on QQQ')}>
              New strategy
            </Button>
          </>
        }
      />
      <div>
        <LedgerHead spark="Recent" />
        <StrategyLedger rows={rows} />
      </div>
      <Foot
        items={[
          `${STRATEGIES.length} strategies`,
          'open a row for its outline',
          'open a strategy to edit its outline',
        ]}
      />
    </Page>
  );
}

function withEdits(items: Item[], edits: Record<string, number>): Item[] {
  return items.map((it) =>
    edits[it.id] !== undefined
      ? { ...it, pct: edits[it.id], weight: `${edits[it.id]}%`, mark: 'add' }
      : it
  );
}

function Builder({ s }: { s: Strategy }) {
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

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3">
        <div>
          <Label>Outline</Label>
          <div className="mt-0.5 text-[12.5px] text-fg-3">
            {state === 'applied'
              ? `Version ${version}, not saved yet`
              : `Version ${s.version} · ${s.versions[0]?.note ?? ''}`}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!prop || state === 'dismissed' ? (
            <Button onClick={() => ask(`Suggest a safer edit to ${s.name}`, s.id)}>
              Ask for an edit
            </Button>
          ) : null}
          <Button variant="primary" disabled={!dirty} className="disabled:opacity-40">
            Save as version {version}
          </Button>
        </div>
      </div>
      <div className="border-y border-line">
        <OutlineView strategy={s} items={items} selected={selected} onSelect={setSelected} />
      </div>
      {state === 'open' && prop && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line py-3">
          <Mono className="text-fg">Copilot</Mono>
          <span className="text-[13px] text-fg">{prop.note}</span>
          <span className="font-mono text-[11.5px] tabular-nums text-fg-3">
            backtest <span className={tone(prop.effect.ret)}>{pts(prop.effect.ret * 100)}</span> ·
            worst {pts(prop.effect.worst * 100)}
          </span>
          <span className="ml-auto flex gap-2">
            <Button variant="primary" onClick={() => setProposal(s.id, 'applied')}>
              Apply
            </Button>
            <Button onClick={() => setProposal(s.id, 'dismissed')}>Discard</Button>
          </span>
        </div>
      )}
      <div className="flex min-h-[52px] flex-wrap items-center gap-3 py-2.5 text-[12.5px] text-fg-3">
        {sel?.kind === 'asset' && sel.symbol && state !== 'open' ? (
          <>
            <Mono className="text-fg-2">Asset</Mono>
            <span className="text-fg">
              {sel.symbol} · {FUND_NAME[sel.symbol]}
            </span>
            {!sel.pick && (
              <span className="ml-auto inline-flex items-center gap-2">
                Weight
                <Button
                  aria-label="Lower weight"
                  onClick={() =>
                    setEdits((e) => ({ ...e, [sel.id]: Math.max(0, (sel.pct ?? 0) - 5) }))
                  }
                >
                  −
                </Button>
                <span className="w-12 text-center font-mono text-[13px] tabular-nums text-fg">
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
                    Undo edits
                  </Button>
                )}
              </span>
            )}
          </>
        ) : (
          <span>
            {state === 'open'
              ? 'Rows marked + and − are the proposed edit. Apply it to edit from there.'
              : 'Select an asset row to change its weight. Click the caret to fold a branch.'}
          </span>
        )}
      </div>
    </section>
  );
}

export function StrategyPage() {
  const { id = '' } = useParams();
  const s = strategyById(id);
  const { ask } = useAsk();
  if (!s)
    return (
      <Page>
        <p className="text-fg-2">This strategy could not be found.</p>
      </Page>
    );
  const ses = activeSession(s.id);
  const bts = backtestsFor(s.id);
  return (
    <Page context={s.id} placeholder={`Ask about ${s.name}, or ask for an edit`} art="build">
      <PageHead
        eyebrow={
          <>
            <Link to="/d/strategies" className="hover:text-fg">
              Strategies
            </Link>{' '}
            / v{s.version}
          </>
        }
        title={s.name}
        meta={`${s.summary} ${stateLabel(s)} · checks ${s.cadence}`}
        right={
          <>
            <LinkButton to={bts[0] ? `/d/backtests/${bts[0].id}` : '/d/backtests'}>
              Backtest
            </LinkButton>
            {ses ? (
              <LinkButton to={`/d/sessions/${ses.id}`}>Open session</LinkButton>
            ) : (
              <Button>Start session</Button>
            )}
            <Button variant="quiet" onClick={() => ask(`Explain ${s.name}`, s.id)}>
              Ask
            </Button>
          </>
        }
      />
      <Builder key={s.id} s={s} />
      <div className="mt-14 grid gap-12 md:grid-cols-2">
        <div>
          <SectionHead title="Versions" meta={`${s.versions.length} saved`} />
          <div className="border-t border-line">
            {s.versions.map((v) => (
              <div
                key={v.n}
                className="grid grid-cols-[44px_64px_minmax(0,1fr)] items-baseline gap-3 border-b border-line py-2.5 text-[13px]"
              >
                <span className="font-mono text-fg">v{v.n}</span>
                <span className="font-mono text-[12px] text-fg-3">{v.saved}</span>
                <span className="truncate text-fg-2">{v.note}</span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <SectionHead
            title="Backtests"
            meta={bts.length ? 'Nov 2024 to Nov 2026 · benchmark SPY' : 'None yet'}
          />
          <div className="border-t border-line">
            {bts.map((b) => (
              <Link
                key={b.id}
                to={`/d/backtests/${b.id}`}
                className="grid grid-cols-[44px_64px_minmax(0,1fr)_80px] items-baseline gap-3 border-b border-line py-2.5 text-[13px] hover:bg-panel/70"
              >
                <span className="font-mono text-fg">v{b.version}</span>
                <span className="font-mono text-[12px] text-fg-3">{b.ran}</span>
                <span className="font-mono text-[12px] text-fg-3">
                  SPY {pts(b.spy * 100)} · worst {pts(b.worst * 100)}
                </span>
                <span className={`text-right font-mono tabular-nums ${tone(b.ret)}`}>
                  {pts(b.ret * 100)}
                </span>
              </Link>
            ))}
          </div>
        </div>
      </div>
      <Foot
        items={[`Version ${s.version}`, `rebalance ${s.cadence}`, 'edits save as a new version']}
      />
    </Page>
  );
}
