import { useCallback } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { SESSIONS, signedUsd, strategyById, usd, type Session } from '../data';

import { Legend, PerfChart } from './chart';
import { useCopilot } from './copilotContext';
import { Head, Page } from './frame';
import { useListNav } from './keys';
import {
  FUND_NAME,
  FUND_TODAY,
  pts,
  pts2,
  sessionActivity,
  sessionValues,
  to,
  tone,
  UPCOMING,
} from './model';
import { OutlineView } from './outline';
import { itemsOf } from './outlineModel';
import { rowClass } from './styles';
import { Block, Button, Delta, LinkButton, ModeTag, Spark, Stats, TableHead } from './ui';

const COLS =
  'grid-cols-[minmax(0,1fr)_96px] md:grid-cols-[minmax(0,1fr)_64px_64px_150px_112px_96px_minmax(0,160px)_minmax(0,140px)]';

const SHADES = ['bg-chart-1', 'bg-chart-2', 'bg-chart-3', 'bg-chart-4', 'bg-chart-5'];

function HoldsBar({ s }: { s: Session }) {
  if (!s.holds.length) return <span className="font-mono text-[11px] text-fg-3">cash</span>;
  return (
    <span className="flex min-w-0 items-center gap-2">
      <span className="flex h-[5px] w-14 flex-none overflow-hidden rounded-[2px] bg-sunk">
        {s.holds.map((h, i) => (
          <i
            key={h.symbol}
            className={`block h-full ${SHADES[i % 5]}`}
            style={{ width: `${h.weight}%` }}
          />
        ))}
      </span>
      <span className="truncate font-mono text-[11px] text-fg-3">
        {s.holds.map((h) => h.symbol).join(' ')}
      </span>
    </span>
  );
}

export function SessionsList() {
  const nav = useNavigate();
  const open = useCallback((i: number) => nav(to(`/sessions/${SESSIONS[i].id}`)), [nav]);
  const edit = useCallback((i: number) => nav(to(`/strategies/${SESSIONS[i].strategyId}`)), [nav]);
  const [sel, setSel] = useListNav(SESSIONS.length, { open, edit });
  const running = SESSIONS.filter((s) => !s.stoppedOn);
  const total = running.reduce((a, s) => a + s.value, 0);
  const today = running.reduce((a, s) => a + s.today, 0);
  return (
    <Page
      art="live"
      head={
        <Head
          crumb="Sessions"
          title="Sessions"
          figure={
            <span className="font-mono text-[13px] tabular-nums text-fg-2">
              {usd(total)} <Delta v={today}>{signedUsd(today)}</Delta>
            </span>
          }
          meta={`${running.length} running · 1 stopped · on your Alpaca account, paper and live`}
        />
      }
    >
      <Block title="All sessions" right={<Legend main="Session" />} className="col-span-12">
        <TableHead cols={COLS}>
          <span>Session</span>
          <span className="hidden md:block">Mode</span>
          <span className="hidden md:block">Started</span>
          <span className="hidden md:block">Since start</span>
          <span className="hidden text-right md:block">Value</span>
          <span className="text-right">Today</span>
          <span className="hidden md:block">Holds</span>
          <span className="hidden md:block">Next</span>
        </TableHead>
        {SESSIONS.map((s, i) => {
          const st = strategyById(s.strategyId);
          const { w, since } = sessionValues(s);
          return (
            <div
              key={s.id}
              role="row"
              aria-selected={i === sel}
              onMouseEnter={() => setSel(i)}
              onClick={() => open(i)}
              className={`${rowClass(i === sel)} ${COLS} ${s.stoppedOn ? 'text-fg-3' : ''}`}
            >
              <span className="flex min-w-0 items-baseline gap-2">
                <span className={`truncate font-medium ${s.stoppedOn ? 'text-fg-2' : 'text-fg'}`}>
                  {st?.name}
                </span>
                <span className="flex-none font-mono text-[10.5px] text-fg-3">v{s.version}</span>
              </span>
              <span className="hidden md:block">
                <ModeTag mode={s.mode} />
              </span>
              <span className="hidden font-mono text-[11.5px] text-fg-3 md:block">{s.started}</span>
              <span className="hidden items-center gap-2 md:flex">
                <Spark values={w.main} bench={w.bench} width={80} height={18} />
                <Delta v={since} className="text-[11.5px]">
                  {pts(since * 100)}
                </Delta>
              </span>
              <span className="hidden text-right font-mono text-[12.5px] tabular-nums text-fg md:block">
                {usd(s.value)}
              </span>
              <span className="text-right">
                {s.stoppedOn ? (
                  <span className="font-mono text-[11.5px] text-fg-3">stopped {s.stoppedOn}</span>
                ) : (
                  <Delta v={s.today} className="text-[12.5px]">
                    {signedUsd(s.today)}
                  </Delta>
                )}
              </span>
              <span className="hidden min-w-0 md:block">
                <HoldsBar s={s} />
              </span>
              <span className="hidden truncate text-[12px] text-fg-2 md:block">
                {s.next ?? 'Positions closed'}
              </span>
            </div>
          );
        })}
      </Block>
    </Page>
  );
}

export function SessionPage() {
  const { id = '' } = useParams();
  const { openBar } = useCopilot();
  const s = SESSIONS.find((x) => x.id === id);
  const st = s ? strategyById(s.strategyId) : undefined;
  if (!s || !st)
    return (
      <Page head={<Head crumb="Sessions" title="Not found" />}>
        <p className="col-span-12 text-fg-2">This session could not be found.</p>
      </Page>
    );
  const { w, first, since } = sessionValues(s);
  const spySince = w.bench[w.bench.length - 1];
  const next = UPCOMING.find((u) => u.session === s.id);
  return (
    <Page
      art="live"
      head={
        <Head
          crumb={
            <>
              <Link to={to('/sessions')} className="hover:text-fg">
                Sessions
              </Link>{' '}
              / {s.mode} / v{s.version}
            </>
          }
          title={st.name}
          figure={
            <span className="inline-flex items-baseline gap-3 font-mono text-[15px] tabular-nums text-fg">
              {usd(s.value)}
              {!s.stoppedOn && (
                <Delta v={s.today} className="text-[12.5px]">
                  {signedUsd(s.today)} today
                </Delta>
              )}
            </span>
          }
          meta={`started ${s.started}${s.stoppedOn ? ` · stopped ${s.stoppedOn}` : ''} · ${s.next ?? 'not trading'}`}
          right={
            <>
              {!s.stoppedOn ? (
                <>
                  <Button>Pause</Button>
                  <Button>Stop</Button>
                </>
              ) : (
                <Button variant="primary">Restart</Button>
              )}
              <LinkButton to={to(`/strategies/${st.id}`)} k="e">
                Edit strategy
              </LinkButton>
              <Button variant="quiet" k="/" onClick={() => openBar(st.id)}>
                Ask
              </Button>
            </>
          }
        />
      }
    >
      <Block
        title="Session vs SPY"
        right={<Legend main="Session" />}
        className="col-span-12 lg:col-span-8"
      >
        <Stats
          className="border-b border-line"
          items={[
            {
              label: 'Since start',
              value: <span className={tone(since)}>{pts(since * 100)}</span>,
              sub: `SPY ${pts(spySince)}`,
            },
            { label: 'Gain', value: signedUsd(s.value - first), sub: `from ${usd(first)}` },
            {
              label: 'Holdings',
              value: s.holds.length || 'cash',
              sub: s.holds.map((h) => h.symbol).join(' ') || '·',
            },
            {
              label: 'Mode',
              value: s.mode,
              sub: s.mode === 'live' ? 'real money' : 'Alpaca paper',
            },
          ]}
        />
        <div className="px-3 pb-2 pt-3">
          <PerfChart w={w} height={220} mainLabel="Session" ddHeight={44} />
        </div>
      </Block>
      <div className="col-span-12 grid content-start gap-3 lg:col-span-4">
        <Block title="Holdings" meta={s.holds.length ? 'weights at the last price' : 'all cash'}>
          {s.holds.map((h) => {
            const t = FUND_TODAY[h.symbol] ?? 0;
            return (
              <div
                key={h.symbol}
                className={`${rowClass(false)} grid-cols-[44px_minmax(0,1fr)_40px_84px_56px]`}
              >
                <span className="font-mono text-[12px] font-medium text-fg">{h.symbol}</span>
                <span className="truncate text-[12px] text-fg-3">{FUND_NAME[h.symbol]}</span>
                <span className="text-right font-mono text-[11.5px] tabular-nums text-fg-2">
                  {h.weight.toFixed(0)}%
                </span>
                <span className="text-right font-mono text-[12px] tabular-nums text-fg">
                  {usd((s.value * h.weight) / 100)}
                </span>
                <Delta v={t} className="text-right text-[11.5px]">
                  {pts2(t)}
                </Delta>
              </div>
            );
          })}
          {s.holds.length === 0 && (
            <p className="m-0 px-3 py-2 text-[12.5px] text-fg-3">
              Positions were closed when it stopped.
            </p>
          )}
        </Block>
        {next && (
          <Block title="Next" meta={next.when}>
            <div className="px-3 py-2">
              <div className="text-[12.5px] text-fg">{next.what}</div>
              <div className="font-mono text-[11px] text-fg-3">{next.detail}</div>
            </div>
          </Block>
        )}
        <Block title="Activity" meta="newest first">
          {sessionActivity(s).map((a, i) => (
            <div
              key={i}
              className={`${rowClass(false)} grid-cols-[48px_minmax(0,140px)_minmax(0,1fr)] cursor-default`}
            >
              <span className="font-mono text-[11px] text-fg-3">{a.when}</span>
              <span className="truncate text-[12.5px] text-fg">{a.what}</span>
              <span className="truncate text-[11.5px] text-fg-3">{a.detail}</span>
            </div>
          ))}
        </Block>
      </div>
      <Block
        title="What it holds and why"
        meta="today's path in ink"
        className="col-span-12 lg:col-span-8"
      >
        <OutlineView strategy={st} items={itemsOf(st.name, st.cadence, st.rules)} />
      </Block>
    </Page>
  );
}
