import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { backtestsFor, STRATEGIES, stateLabel, strategyById, type Strategy } from '../data';

import { useAsk } from './askContext';
import { Page, PageHead } from './frame';
import { activeSession, FUND_NAME, PROPOSALS, pts, tone } from './model';
import {
  outlineItems,
  proposalState,
  SORTED_STRATEGIES,
  STRATEGY_COLS,
  strategyRows,
  strategyScope,
} from './rows';
import type { Scope } from './scope';
import { ScopeSheet } from './sheet';
import { LedgerTree, type LRow } from './tree';
import { Button, Foot, LinkButton, Mono, SectionHead } from './ui';

const NO_EDITS: Record<string, number> = {};
const DEFAULT = strategyById('recession-radar') ?? STRATEGIES[0];

export function StrategiesList() {
  const { ask, proposals, setProposal } = useAsk();
  const rows = useMemo(
    () => SORTED_STRATEGIES.flatMap((s) => strategyRows(s, { proposals, setProposal })),
    [proposals, setProposal]
  );
  const [scope, setScope] = useState<Scope>(() => strategyScope(DEFAULT));
  const count = (st: Strategy['state']) => STRATEGIES.filter((s) => s.state === st).length;
  return (
    <Page ask={false}>
      <PageHead
        eyebrow="Nov 20, 2026 · 12:04 ET"
        title="Strategies"
        meta={`${count('running')} running · ${count('stopped')} stopped · ${count('never-run')} never run · ${count('draft')} draft`}
        right={
          <Button variant="primary" size="md" onClick={() => ask('Draft a trend strategy on QQQ')}>
            New strategy
          </Button>
        }
      />
      <ScopeSheet scope={scope}>
        <LedgerTree
          label="Strategies"
          name="Strategy"
          rows={rows}
          cols={STRATEGY_COLS}
          selected={scope.key}
          onSelect={(r) => r.scope && setScope(r.scope)}
          closedAtStart={SORTED_STRATEGIES.filter((s) => s.state !== 'running').map((s) => s.id)}
        />
      </ScopeSheet>
      <Foot
        items={[
          `${STRATEGIES.length} strategies`,
          'running ones open, the rest folded',
          'double-click a strategy to edit it',
        ]}
      />
    </Page>
  );
}

function Builder({
  s,
  onScope,
  scopeKey,
}: {
  s: Strategy;
  onScope: (sc: Scope) => void;
  scopeKey: string;
}) {
  const { proposals, setProposal, ask } = useAsk();
  const api = useMemo(() => ({ proposals, setProposal }), [proposals, setProposal]);
  const state = proposalState(s.id, api);
  const prop = PROPOSALS[s.id];
  const [selected, setSelected] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, number>>({});
  const shown = state === 'open' ? NO_EDITS : edits;
  const rows = useMemo(() => strategyRows(s, api, 0, shown), [s, api, shown]);
  const items = useMemo(() => outlineItems(s, api), [s, api]);
  const itemId = selected?.slice(s.id.length + 1);
  const sel = items.find((i) => i.id === itemId);
  const pct = sel ? (edits[sel.id] ?? sel.pct ?? 0) : 0;
  const dirty = Object.keys(edits).length > 0 || state === 'applied';
  const version = s.version + 1;
  const onSelect = (r: LRow) => {
    setSelected(r.id);
    if (r.scope) onScope(r.scope);
  };

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-2.5 md:px-6">
        <span className="text-[12.5px] text-fg-3">
          {state === 'applied'
            ? `Version ${version}, not saved yet`
            : dirty
              ? `Edited, saves as version ${version}`
              : `Version ${s.version} · ${s.versions[0]?.note ?? ''}`}
        </span>
        <span className="flex items-center gap-2">
          {(!prop || state === 'dismissed') && (
            <Button onClick={() => ask(`Suggest a safer edit to ${s.name}`, s.id)}>
              Ask for an edit
            </Button>
          )}
          <Button variant="primary" disabled={!dirty} className="disabled:opacity-40">
            Save as version {version}
          </Button>
        </span>
      </div>
      <LedgerTree
        label={`${s.name} outline`}
        name="Outline"
        rows={rows}
        cols={STRATEGY_COLS.filter((c) => c.key !== 'backtest')}
        selected={scopeKey}
        onSelect={onSelect}
      />
      <div className="flex min-h-[52px] flex-wrap items-center gap-3 border-t border-line px-4 py-2.5 text-[12.5px] text-fg-3 md:px-6">
        {sel?.kind === 'asset' && sel.symbol && state !== 'open' && !sel.pick ? (
          <>
            <Mono className="text-fg-2">Asset</Mono>
            <span className="text-fg">
              {sel.symbol} · {FUND_NAME[sel.symbol]}
            </span>
            <span className="ml-auto inline-flex items-center gap-2">
              Weight
              <Button
                aria-label="Lower weight"
                onClick={() => setEdits((e) => ({ ...e, [sel.id]: Math.max(0, pct - 5) }))}
              >
                −
              </Button>
              <span className="w-12 text-center font-mono text-[13px] tabular-nums text-fg">
                {pct}%
              </span>
              <Button
                aria-label="Raise weight"
                onClick={() => setEdits((e) => ({ ...e, [sel.id]: Math.min(100, pct + 5) }))}
              >
                +
              </Button>
              {Object.keys(edits).length > 0 && (
                <Button variant="quiet" onClick={() => setEdits({})}>
                  Undo edits
                </Button>
              )}
            </span>
          </>
        ) : (
          <span>
            {state === 'open'
              ? 'Rows marked + and − are the Copilot edit. Apply it to keep editing from there.'
              : 'Select an asset to change its weight. Any row scopes the chart above.'}
          </span>
        )}
      </div>
    </>
  );
}

export function StrategyPage() {
  const { id = '' } = useParams();
  const s = strategyById(id);
  const { ask } = useAsk();
  const [scope, setScope] = useState<Scope | null>(null);
  if (!s)
    return (
      <Page ask={false}>
        <p className="text-fg-2">This strategy could not be found.</p>
      </Page>
    );
  const sc = scope && scope.path[1] === s.name ? scope : strategyScope(s);
  const ses = activeSession(s.id);
  const bts = backtestsFor(s.id);
  return (
    <Page ask={false} art="build">
      <PageHead
        eyebrow={
          <>
            <Link to="/e/strategies" className="hover:text-fg">
              Strategies
            </Link>{' '}
            / v{s.version}
          </>
        }
        title={s.name}
        meta={`${s.summary} ${stateLabel(s)} · checks ${s.cadence}`}
        right={
          <>
            <LinkButton to={bts[0] ? `/e/backtests/${bts[0].id}` : '/e/backtests'}>
              Backtest
            </LinkButton>
            {ses ? (
              <LinkButton to={`/e/sessions/${ses.id}`}>Open session</LinkButton>
            ) : (
              <Button>Start session</Button>
            )}
            <Button variant="quiet" onClick={() => ask(`Explain ${s.name}`, s.id)}>
              Ask
            </Button>
          </>
        }
      />
      <ScopeSheet scope={sc}>
        <Builder key={s.id} s={s} onScope={setScope} scopeKey={sc.key} />
      </ScopeSheet>
      <div className="mt-12 grid gap-12 md:grid-cols-2">
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
                to={`/e/backtests/${b.id}`}
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
