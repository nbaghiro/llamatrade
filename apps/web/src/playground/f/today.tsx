import { useState } from 'react';
import { Link } from 'react-router-dom';

import { ACCOUNT, pct, signedUsd, usd } from '../data';

import { Legend, PerfChart } from './chart';
import { SUGGESTED } from './commands';
import { TurnView } from './copilot';
import { useCopilot } from './copilotContext';
import { Head, Page } from './frame';
import { Ledger } from './ledger';
import {
  accountWindow,
  ASSET_CLASSES,
  dayLabel,
  drawdown,
  FILLS,
  RANGES,
  RESTING,
  RUNNING,
  pts,
  sessionName,
  to,
  tone,
  UPCOMING,
  type Range,
} from './model';
import { Block, Delta, Kbd, Mono, Seg, Stats } from './ui';

function CopilotBlock() {
  const { turns, submit, run, openBar } = useCopilot();
  const [q, setQ] = useState('');
  const last = turns.slice(-2);
  const n = turns.length / 2;
  return (
    <Block
      title="Copilot"
      meta={`${n} ${n === 1 ? 'question' : 'questions'} today`}
      right={
        <button
          type="button"
          onClick={() => openBar()}
          className="font-mono text-[10.5px] text-fg-3 hover:text-fg"
        >
          Full thread <Kbd className="ml-1">⌘K</Kbd>
        </button>
      }
      className="col-span-12 lg:col-span-7"
    >
      <div id="f-copilot" className="flex h-full scroll-mt-16 flex-col">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(q);
            setQ('');
          }}
          className="flex h-11 items-center gap-3 border-b border-line px-3 focus-within:bg-panel/40"
        >
          <span aria-hidden="true" className="font-mono text-[15px] text-fg-3">
            ›
          </span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ask, or type a command: backtest recession radar 5y"
            aria-label="Ask Copilot or run a command"
            className="min-w-0 flex-1 bg-transparent font-mono text-[13px] text-fg outline-none placeholder:text-fg-3"
          />
          <Kbd>↵</Kbd>
        </form>
        <div className="divide-y divide-line px-3">
          {last.map((t) => (
            <TurnView key={t.id} turn={t} />
          ))}
        </div>
        <div className="mt-auto flex flex-wrap items-center gap-1.5 border-t border-line px-3 py-2">
          <Mono className="mr-1 text-fg-3">Try</Mono>
          {SUGGESTED.slice(1).map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => run(s.action)}
              className="h-6 rounded-[4px] border border-line px-2 font-mono text-[11px] text-fg-2 transition-colors hover:border-line-strong hover:text-fg"
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
    </Block>
  );
}

function AccountBlock() {
  const [range, setRange] = useState<Range>('3M');
  const w = accountWindow(range);
  const n = w.main.length;
  const ea = w.main[n - 1];
  const eb = w.bench[n - 1];
  const dd = Math.min(...drawdown(w.main));
  const ddb = Math.min(...drawdown(w.bench));
  return (
    <Block
      title="Account vs SPY"
      right={
        <Seg
          label="Range"
          value={range}
          onChange={setRange}
          options={RANGES.map((r) => ({ key: r, label: r }))}
        />
      }
      className="col-span-12 self-start lg:col-span-5"
    >
      <Stats
        className="border-b border-line"
        items={[
          {
            label: `Return ${range}`,
            value: <span className={tone(ea)}>{pts(ea)}</span>,
            sub: `SPY ${pts(eb)}`,
          },
          {
            label: 'vs SPY',
            value: `${ea - eb >= 0 ? '+' : '−'}${Math.abs(ea - eb).toFixed(1)} pts`,
            sub: ea >= eb ? 'ahead' : 'behind',
          },
          { label: 'Max drawdown', value: pts(dd), sub: `SPY ${pts(ddb)}` },
        ]}
      />
      <div className="px-3 pb-2 pt-2.5">
        <div className="mb-1.5">
          <Legend markers={w.markers.length > 0} />
        </div>
        <PerfChart w={w} height={176} />
      </div>
      {w.markers.length > 0 && (
        <ol className="m-0 grid list-none grid-cols-1 gap-x-4 border-t border-line px-3 py-2 sm:grid-cols-2">
          {w.markers.map((m) => (
            <li key={m.n} className="flex h-6 min-w-0 items-center gap-2 text-[11.5px] text-fg-2">
              <i className="grid h-3.5 w-3.5 flex-none place-items-center rounded-[2px] border border-line-strong font-mono text-[9px] not-italic text-fg">
                {m.n}
              </i>
              <span className="w-[42px] flex-none font-mono text-[10.5px] text-fg-3">
                {dayLabel(w.dates[m.i])}
              </span>
              <span className="truncate">{m.label.replace(' started on ', ' on ')}</span>
            </li>
          ))}
        </ol>
      )}
    </Block>
  );
}

function NextBlock() {
  return (
    <Block title="Next" meta="what sessions do next">
      {UPCOMING.map((u) => {
        return (
          <Link
            key={u.session}
            to={to(`/sessions/${u.session}`)}
            className="grid grid-cols-[52px_minmax(0,1fr)] gap-x-3 border-b border-line px-3 py-2 last:border-b-0 hover:bg-panel"
          >
            <span className="font-mono text-[12px] tabular-nums text-fg">{u.when}</span>
            <span className="min-w-0">
              <span className="block truncate text-[12.5px] text-fg">
                {sessionName(u.session)} <span className="text-fg-3">· {u.what.toLowerCase()}</span>
              </span>
              <span className="block truncate font-mono text-[11px] text-fg-3">{u.detail}</span>
            </span>
          </Link>
        );
      })}
    </Block>
  );
}

function FillsBlock() {
  return (
    <Block title="Fills" meta="none today · last 5">
      {FILLS.map((f, i) => (
        <Link
          key={i}
          to={to(`/sessions/${f.session}`)}
          className="grid h-8 grid-cols-[48px_36px_44px_minmax(0,1fr)_64px] items-center gap-2 border-b border-line px-3 font-mono text-[11.5px] tabular-nums last:border-b-0 hover:bg-panel"
        >
          <span className="text-fg-3">{f.when}</span>
          <span className={f.side === 'Buy' ? 'text-fg' : 'text-fg-2'}>{f.side.toLowerCase()}</span>
          <span className="font-medium text-fg">{f.symbol}</span>
          <span className="truncate font-sans text-[12px] text-fg-3">{sessionName(f.session)}</span>
          <span className="text-right text-fg-2">{f.price}</span>
        </Link>
      ))}
    </Block>
  );
}

const shade = (i: number) => `rgb(var(--fg) / ${Math.max(0.14, 0.9 - i * 0.13).toFixed(2)})`;

function HeldBlock() {
  return (
    <Block
      title="Held"
      right={
        <Link to={to('/portfolio')} className="font-mono text-[10.5px] text-fg-3 hover:text-fg">
          Portfolio <Kbd className="ml-1">5</Kbd>
        </Link>
      }
    >
      <div className="px-3 pt-3">
        <div className="flex h-2 w-full overflow-hidden rounded-[2px]">
          {ASSET_CLASSES.map((c, i) => (
            <span
              key={c.name}
              className="block h-full border-r border-canvas last:border-r-0"
              style={{
                width: `${(c.value / ACCOUNT.total) * 100}%`,
                background:
                  c.name === 'Cash'
                    ? 'repeating-linear-gradient(135deg, var(--hatch) 0 2px, transparent 2px 5px)'
                    : shade(i),
              }}
            />
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-x-4 px-3 py-2">
        {ASSET_CLASSES.map((c, i) => (
          <div key={c.name} className="flex h-6 min-w-0 items-center gap-2 text-[11.5px]">
            <i
              className={`h-2 w-2 flex-none rounded-[1px] ${c.name === 'Cash' ? 'border border-fg-3' : ''}`}
              style={c.name === 'Cash' ? undefined : { background: shade(i) }}
            />
            <span className="min-w-0 flex-1 truncate text-fg-2">{c.name}</span>
            <span className="font-mono tabular-nums text-fg">
              {((c.value / ACCOUNT.total) * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </Block>
  );
}

export function Today() {
  return (
    <Page
      head={
        <Head
          crumb="Today · Fri Nov 20 · 12:04 ET"
          title={<span className="font-mono tracking-[-0.04em]">{usd(ACCOUNT.total)}</span>}
          figure={
            <Delta v={ACCOUNT.today} className="text-[13px]">
              {signedUsd(ACCOUNT.today)} {pct(ACCOUNT.today / (ACCOUNT.total - ACCOUNT.today), 2)}
            </Delta>
          }
          meta={`live ${usd(ACCOUNT.live)} · paper ${usd(ACCOUNT.paper)} · ${RUNNING.length} sessions running`}
        />
      }
    >
      <CopilotBlock />
      <AccountBlock />
      <Block
        title="Strategies and sessions"
        meta={`${RUNNING.length} running · ${RESTING.length} not running`}
        right={
          <span className="hidden items-center gap-1.5 font-mono text-[10.5px] text-fg-3 sm:inline-flex">
            <Kbd>space</Kbd> preview
          </span>
        }
        className="col-span-12 self-start lg:col-span-8"
      >
        <Ledger rows={[...RUNNING, ...RESTING]} />
      </Block>
      <div className="col-span-12 grid content-start gap-3 lg:col-span-4">
        <NextBlock />
        <FillsBlock />
        <HeldBlock />
      </div>
    </Page>
  );
}
