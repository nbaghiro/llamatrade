import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import {
  backtestsFor,
  signedUsd,
  STRATEGIES,
  stateLabel,
  strategyById,
  usd,
  type Strategy,
} from '../data';

import { PerfChart } from './chart';
import { useCopilot } from './copilotContext';
import { Head, Page } from './frame';
import { useListNav } from './keys';
import { Ledger } from './ledger';
import { activeSession, backtestWindow, FUND_NAME, PROPOSALS, pts, to, tone } from './model';
import { OutlineView } from './outline';
import { diffItems, itemsOf, type Item } from './outlineModel';
import { rowClass } from './styles';
import { Block, Button, Delta, Kbd, LinkButton, ModeTag, Mono, Seg, Stats } from './ui';

type Filter = 'all' | 'running' | 'resting' | 'draft';

export function StrategiesList() {
  const { run } = useCopilot();
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
    <Page
      art="build"
      head={
        <Head
          crumb="Strategies"
          title="Strategies"
          meta="3 running · 1 stopped · 2 never run · 1 draft"
          right={
            <Button
              variant="primary"
              onClick={() => run({ type: 'ask', prompt: 'Draft a trend strategy on QQQ' })}
            >
              New strategy
            </Button>
          }
        />
      }
    >
      <Block
        title={`${rows.length} strategies`}
        right={
          <Seg
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
        }
        className="col-span-12"
      >
        <Ledger key={filter} rows={rows} wide initiallyOpen="recession-radar" />
      </Block>
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
  const { proposals, setProposal, submit } = useCopilot();
  const prop = PROPOSALS[s.id];
  const state = prop ? (proposals[s.id] ?? 'open') : 'dismissed';
  const [edits, setEdits] = useState<Record<string, number>>({});
  const [q, setQ] = useState('');
  const base = useMemo(
    () => itemsOf(s.name, s.cadence, state === 'applied' && prop ? prop.rules : s.rules),
    [s, state, prop]
  );
  const items = useMemo(() => {
    if (state === 'open' && prop) return diffItems(base, itemsOf(s.name, s.cadence, prop.rules));
    return withEdits(base, edits);
  }, [base, state, prop, s, edits]);
  const [sel, setSel] = useListNav(items.length, {}, 0);
  const selected = items[sel];
  const dirty = Object.keys(edits).length > 0 || state === 'applied';
  const version = s.version + 1;
  const canEdit = selected?.kind === 'asset' && !selected.pick && state !== 'open';

  const nudge = useCallback(
    (d: number) => {
      if (!canEdit || !selected) return;
      setEdits((e) => ({
        ...e,
        [selected.id]: Math.max(0, Math.min(100, (selected.pct ?? 0) + d)),
      }));
    },
    [canEdit, selected]
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      if (document.documentElement.hasAttribute('data-fbar')) return;
      if (e.key === '+' || e.key === '=') nudge(5);
      if (e.key === '-') nudge(-5);
      if (state === 'open' && prop && e.key === 'a') setProposal(s.id, 'applied');
      if (state === 'open' && prop && e.key === 'd') setProposal(s.id, 'dismissed');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [nudge, state, prop, s.id, setProposal]);

  return (
    <Block
      title="Outline"
      meta={
        state === 'applied'
          ? `v${version} · not saved yet`
          : state === 'open'
            ? `v${s.version} · Copilot proposes v${prop?.version}`
            : `v${s.version} · ${s.versions[0]?.note ?? ''}`
      }
      right={
        <Button variant="primary" disabled={!dirty} className="disabled:opacity-40" k="⌘S">
          Save v{version}
        </Button>
      }
      className="col-span-12 self-start lg:col-span-8"
    >
      <OutlineView
        strategy={s}
        items={items}
        selected={selected?.id}
        onSelect={(id) =>
          setSel(
            Math.max(
              0,
              items.findIndex((i) => i.id === id)
            )
          )
        }
      />
      {state === 'open' && prop && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line bg-panel/50 px-3 py-2">
          <Mono className="text-fg">Copilot</Mono>
          <span className="text-[12.5px] text-fg">{prop.note}</span>
          <span className="font-mono text-[11px] tabular-nums text-fg-3">
            backtest <span className={tone(prop.effect.ret)}>{pts(prop.effect.ret * 100)}</span> ·
            worst {pts(prop.effect.worst * 100)}
          </span>
          <span className="ml-auto flex gap-2">
            <Button variant="primary" k="a" onClick={() => setProposal(s.id, 'applied')}>
              Apply
            </Button>
            <Button k="d" onClick={() => setProposal(s.id, 'dismissed')}>
              Discard
            </Button>
          </span>
        </div>
      )}
      <div className="flex min-h-8 flex-wrap items-center gap-3 border-t border-line px-3 py-1 font-mono text-[11px] text-fg-3">
        {canEdit && selected?.symbol ? (
          <>
            <Mono className="text-fg-2">Asset</Mono>
            <span className="font-sans text-[12.5px] text-fg">
              {selected.symbol} · {FUND_NAME[selected.symbol]}
            </span>
            <span className="ml-auto inline-flex items-center gap-2">
              <Button aria-label="Lower weight" k="−" onClick={() => nudge(-5)}>
                5
              </Button>
              <span className="w-10 text-center text-[12.5px] tabular-nums text-fg">
                {selected.pct}%
              </span>
              <Button aria-label="Raise weight" k="+" onClick={() => nudge(5)}>
                5
              </Button>
              {Object.keys(edits).length > 0 && (
                <Button variant="quiet" onClick={() => setEdits({})}>
                  Undo
                </Button>
              )}
            </span>
          </>
        ) : (
          <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="inline-flex items-center gap-1.5">
              <Kbd>j</Kbd>
              <Kbd>k</Kbd> move
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Kbd>+</Kbd>
              <Kbd>−</Kbd> weight on an asset row
            </span>
            {state === 'open' && <span>rows marked + and − are the proposed edit</span>}
          </span>
        )}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!q.trim()) return;
          if (prop && state !== 'applied') setProposal(s.id, 'open');
          else submit(q, s.id);
          setQ('');
        }}
        className="flex h-10 items-center gap-3 border-t border-line px-3"
      >
        <Mono className="text-fg-3">Copilot</Mono>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={`Ask for an edit to ${s.name}`}
          aria-label="Ask Copilot for an edit"
          className="min-w-0 flex-1 bg-transparent font-mono text-[12.5px] text-fg outline-none placeholder:text-fg-3"
        />
        <Kbd>↵</Kbd>
      </form>
    </Block>
  );
}

export function StrategyPage() {
  const { id = '' } = useParams();
  const s = strategyById(id);
  const nav = useNavigate();
  const { openBar } = useCopilot();
  const bts = useMemo(() => (s ? backtestsFor(s.id) : []), [s]);
  const ses = s ? activeSession(s.id) : undefined;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      if (document.documentElement.hasAttribute('data-fbar')) return;
      if (e.metaKey || e.ctrlKey) return;
      if (e.key === 'b') nav(bts[0] ? to(`/backtests/${bts[0].id}`) : to('/backtests'));
      if (e.key === 's' && ses) nav(to(`/sessions/${ses.id}`));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [nav, bts, ses]);
  if (!s)
    return (
      <Page head={<Head crumb="Strategies" title="Not found" />}>
        <p className="col-span-12 text-fg-2">This strategy could not be found.</p>
      </Page>
    );
  const b = bts[0];
  return (
    <Page
      art="build"
      head={
        <Head
          crumb={
            <>
              <Link to={to('/strategies')} className="hover:text-fg">
                Strategies
              </Link>{' '}
              / v{s.version} / {s.cadence}
            </>
          }
          title={s.name}
          figure={<ModeTag mode={ses?.mode} />}
          meta={`${s.summary} ${stateLabel(s)}.`}
          right={
            <>
              <LinkButton to={b ? to(`/backtests/${b.id}`) : to('/backtests')} k="b">
                Backtest
              </LinkButton>
              {ses ? (
                <LinkButton to={to(`/sessions/${ses.id}`)} k="s">
                  Session
                </LinkButton>
              ) : (
                <Button>Start paper session</Button>
              )}
              <Button variant="quiet" k="/" onClick={() => openBar(s.id)}>
                Ask
              </Button>
            </>
          }
        />
      }
    >
      <Builder key={s.id} s={s} />
      <div className="col-span-12 grid content-start gap-3 lg:col-span-4">
        <Block title="Last backtest" meta={b ? `v${b.version} · ${b.range}` : 'none yet'}>
          {b ? (
            <>
              <Stats
                className="border-b border-line"
                items={[
                  {
                    label: 'Return',
                    value: <span className={tone(b.ret)}>{pts(b.ret * 100)}</span>,
                    sub: `SPY ${pts(b.spy * 100)}`,
                  },
                  { label: 'Worst', value: pts(b.worst * 100) },
                  { label: 'Sharpe', value: b.sharpe.toFixed(2) },
                ]}
              />
              <div className="px-3 pb-1 pt-2">
                <PerfChart w={backtestWindow(b)} height={112} mainLabel={s.name} />
              </div>
            </>
          ) : (
            <p className="m-0 px-3 py-2.5 text-[12.5px] text-fg-3">Not backtested yet.</p>
          )}
        </Block>
        <Block title="Session" meta={ses ? `${ses.mode} · since ${ses.started}` : 'not running'}>
          {ses ? (
            <Link to={to(`/sessions/${ses.id}`)} className="block hover:bg-panel">
              <div className="grid grid-cols-2 font-mono text-[12.5px] tabular-nums">
                <div className="px-3 py-2">
                  <div className="text-fg">{usd(ses.value)}</div>
                  <Delta v={ses.today} className="text-[11px]">
                    {signedUsd(ses.today)} today
                  </Delta>
                </div>
                <div className="border-l border-line px-3 py-2">
                  <div className="truncate text-fg">{ses.holds.map((h) => h.symbol).join(' ')}</div>
                  <div className="truncate text-[11px] text-fg-3">{ses.next}</div>
                </div>
              </div>
            </Link>
          ) : (
            <div className="flex items-center justify-between px-3 py-2">
              <span className="text-[12.5px] text-fg-3">Run it on paper first.</span>
              <Button>Start paper session</Button>
            </div>
          )}
        </Block>
        <Block title="Versions" meta={`${s.versions.length} saved`}>
          {s.versions.map((v, i) => (
            <div key={v.n} className={`${rowClass(false)} grid-cols-[32px_48px_minmax(0,1fr)]`}>
              <span className={`font-mono text-[12px] ${i === 0 ? 'text-fg' : 'text-fg-3'}`}>
                v{v.n}
              </span>
              <span className="font-mono text-[11px] text-fg-3">{v.saved}</span>
              <span className="truncate text-[12.5px] text-fg-2">{v.note}</span>
            </div>
          ))}
        </Block>
      </div>
    </Page>
  );
}
