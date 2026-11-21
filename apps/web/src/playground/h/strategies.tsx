import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import {
  BACKTESTS,
  backtestsFor,
  signedUsd,
  STRATEGIES,
  stateLabel,
  strategyById,
  usd,
  type Strategy,
} from '../data';

import { useAsk } from './askContext';
import { Briefs, Stat } from './briefs';
import { PerfChart } from './chart';
import { Dateline, Lead, Page } from './frame';
import {
  activeSession,
  backtestWindow,
  FUND_NAME,
  lastBacktest,
  PROPOSALS,
  pts,
  sessionValues,
  tone,
} from './model';
import { OutlineView } from './outline';
import { diffItems, itemsOf, type Item } from './outlineModel';
import { Feature } from './stories';
import { Button, Kicker, LinkButton, Mono, Segmented, Spread } from './ui';

type Filter = 'all' | 'running' | 'resting';

function listHeadline(): string {
  const running = STRATEGIES.filter((s) => s.state === 'running').length;
  const beat = BACKTESTS.filter((b) => b.ret > b.spy);
  const who = beat.map((b) => strategyById(b.strategyId)?.name ?? '');
  const beatLine =
    beat.length === 0
      ? 'none beat SPY in backtest'
      : beat.length === 1
        ? `only ${who[0]} beat SPY in backtest`
        : `${beat.length} beat SPY in backtest`;
  return `${running} running, ${beatLine}`;
}

export function StrategiesList() {
  const { ask } = useAsk();
  const [filter, setFilter] = useState<Filter>('all');
  const rows = STRATEGIES.filter((s) =>
    filter === 'all' ? true : filter === 'running' ? s.state === 'running' : s.state !== 'running'
  );
  const versions = STRATEGIES.flatMap((s) =>
    s.versions.slice(0, 1).map((v) => ({
      when: v.saved,
      title: `${s.name} v${v.n}`,
      detail: v.note,
      to: `/h/strategies/${s.id}`,
    }))
  );
  const ranked = [...BACKTESTS].sort((a, b) => b.ret - a.ret);
  return (
    <Page ask={{ placeholder: 'Ask about your strategies, or describe a new one' }}>
      <Lead
        kicker={`Strategies · ${STRATEGIES.length} in the book`}
        headline={listHeadline()}
        deck="Each strategy with its outline. Open one to edit it."
        right={
          <Button variant="primary" onClick={() => ask('Draft a trend strategy on QQQ')}>
            New strategy
          </Button>
        }
      />
      <Spread
        main={
          <>
            <Kicker
              right={
                <Segmented
                  label="Filter"
                  value={filter}
                  onChange={setFilter}
                  options={[
                    { key: 'all', label: 'All' },
                    { key: 'running', label: 'Running' },
                    { key: 'resting', label: 'Not running' },
                  ]}
                />
              }
            >
              {filter === 'running' ? 'Running' : filter === 'resting' ? 'Not running' : 'All'}
            </Kicker>
            <div className="mt-1">
              {rows.map((s) => (
                <Feature key={s.id} s={s} />
              ))}
            </div>
          </>
        }
        aside={
          <>
            <Briefs
              title="Backtest table"
              right="two years"
              items={ranked.map((b) => ({
                when: pts(b.ret * 100),
                title: strategyById(b.strategyId)?.name ?? '',
                detail: `v${b.version} · SPY ${pts(b.spy * 100)} · worst ${pts(b.worst * 100)}`,
                to: `/h/backtests/${b.id}`,
                tone: b.ret > b.spy ? 'gain' : undefined,
              }))}
            />
            <Briefs title="Latest versions" items={versions} />
          </>
        }
      />
      <Dateline items={[`${STRATEGIES.length} strategies`, 'edits save as a new version']} />
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
      <Kicker
        right={
          state === 'applied'
            ? `Version ${version}, not saved yet`
            : `Version ${s.version} · ${s.versions[0]?.note ?? ''}`
        }
      >
        Outline
      </Kicker>
      <div className="mt-1 overflow-x-auto border-b border-line">
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
              </span>
            )}
          </>
        ) : (
          <span>
            {state === 'open'
              ? 'Rows marked + and − are the proposed edit.'
              : 'Select an asset row to change its weight.'}
          </span>
        )}
        <span className="ml-auto flex items-center gap-2">
          {Object.keys(edits).length > 0 && (
            <Button variant="quiet" onClick={() => setEdits({})}>
              Undo edits
            </Button>
          )}
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
    </section>
  );
}

export function StrategyPage() {
  const { id = '' } = useParams();
  const s = strategyById(id);
  const { ask } = useAsk();
  if (!s)
    return (
      <Page ask={{}}>
        <p className="text-fg-2">This strategy could not be found.</p>
      </Page>
    );
  const ses = activeSession(s.id);
  const bts = backtestsFor(s.id);
  const b = lastBacktest(s.id);
  const sv = ses ? sessionValues(ses) : null;
  return (
    <Page ask={{ context: s.id, placeholder: `Ask about ${s.name}, or ask for an edit` }}>
      <Lead
        kicker={
          <>
            <Link to="/h/strategies" className="hover:text-fg">
              Strategies
            </Link>{' '}
            · v{s.version} · {stateLabel(s)} · checks {s.cadence}
          </>
        }
        headline={s.name}
        deck={s.summary}
        right={
          <>
            <LinkButton to={bts[0] ? `/h/backtests/${bts[0].id}` : '/h/backtests'} size="md">
              Backtest
            </LinkButton>
            {ses ? (
              <LinkButton to={`/h/sessions/${ses.id}`} size="md">
                Open session
              </LinkButton>
            ) : (
              <Button size="md">Start session</Button>
            )}
            <Button size="md" variant="quiet" onClick={() => ask(`Explain ${s.name}`, s.id)}>
              Ask
            </Button>
          </>
        }
      />
      <Spread
        main={
          <>
            <Builder key={s.id} s={s} />
            {b && (
              <div className="mt-12">
                <Kicker right={`v${b.version} · ${b.range}`}>Last backtest against SPY</Kicker>
                <div className="mt-5">
                  <PerfChart
                    w={backtestWindow(b)}
                    height={220}
                    mainLabel={s.name}
                    worst={b.worst * 100}
                  />
                </div>
              </div>
            )}
          </>
        }
        aside={
          <>
            {ses && sv && (
              <section className="mb-9">
                <Kicker right={ses.mode}>Session</Kicker>
                <Stat label="Value">{usd(ses.value)}</Stat>
                <Stat label="Today">
                  <span className={tone(ses.today)}>{signedUsd(ses.today)}</span>
                </Stat>
                <Stat label={`Since ${ses.started}`}>
                  <span className={tone(sv.since)}>{pts(sv.since * 100)}</span>
                </Stat>
              </section>
            )}
            {b && (
              <section className="mb-9">
                <Kicker right={`v${b.version} · ${b.ran}`}>Last backtest</Kicker>
                <Stat label="Return" sub={`SPY ${pts(b.spy * 100)}`}>
                  <span className={tone(b.ret)}>{pts(b.ret * 100)}</span>
                </Stat>
                <Stat label="Max drawdown">{pts(b.worst * 100)}</Stat>
                <Stat label="Sharpe">{b.sharpe.toFixed(2)}</Stat>
              </section>
            )}
            <Briefs
              title="Versions"
              right={`${s.versions.length} saved`}
              items={s.versions.map((v) => ({ when: `v${v.n}`, title: v.saved, detail: v.note }))}
            />
            <Briefs
              title="Backtests"
              empty="No backtests yet."
              items={bts.map((x) => ({
                when: x.ran,
                title: `v${x.version} · ${pts(x.ret * 100)}`,
                detail: `SPY ${pts(x.spy * 100)} · worst ${pts(x.worst * 100)}`,
                to: `/h/backtests/${x.id}`,
              }))}
            />
          </>
        }
      />
      <Dateline
        items={[`Version ${s.version}`, `rebalance ${s.cadence}`, 'edits save as a new version']}
      />
    </Page>
  );
}
