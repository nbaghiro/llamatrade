import { Link, useParams } from 'react-router-dom';

import { SESSIONS, signedUsd, strategyById, usd, type Session } from '../data';

import { useAsk } from './askContext';
import { PerfChart } from './chart';
import { Page, PageHead } from './frame';
import { FUND_NAME, FUND_TODAY, pts, pts2, sessionActivity, sessionValues, tone } from './model';
import { OutlineView } from './outline';
import { itemsOf } from './outlineModel';
import {
  Button,
  Delta,
  Figure,
  Figures,
  Foot,
  Label,
  LinkButton,
  ModeTag,
  Panel,
  SectionHead,
  Spark,
} from './ui';

const COLS =
  'grid-cols-[minmax(0,1fr)_100px] md:grid-cols-[minmax(0,1fr)_70px_120px_120px_100px_150px_130px]';

/** The session's holdings as one thin stacked bar with tickers under it. */
function HoldsBar({ s }: { s: Session }) {
  if (!s.holds.length) return <span className="text-[12px] text-fg-3">Cash</span>;
  const shades = ['bg-chart-1', 'bg-chart-2', 'bg-chart-3', 'bg-chart-4', 'bg-chart-5'];
  return (
    <span className="block">
      <span className="flex h-[5px] w-full overflow-hidden rounded-full bg-sunk">
        {s.holds.map((h, i) => (
          <i
            key={h.symbol}
            className={`block h-full ${shades[i % 5]}`}
            style={{ width: `${h.weight}%` }}
          />
        ))}
      </span>
      <span className="mt-1 block truncate font-mono text-[10.5px] text-fg-3">
        {s.holds.map((h) => h.symbol).join(' ')}
      </span>
    </span>
  );
}

export function SessionsList() {
  const running = SESSIONS.filter((s) => !s.stoppedOn);
  const total = running.reduce((a, s) => a + s.value, 0);
  return (
    <Page ask={{ placeholder: 'Ask about your sessions' }} art="live">
      <PageHead
        eyebrow="Nov 20, 2026 · 12:04 ET"
        title="Sessions"
        meta={`${running.length} running · ${usd(total)} in running sessions · 1 stopped`}
      />
      <Panel className="px-5 pb-2 pt-4 md:px-7">
        <div
          className={`grid ${COLS} gap-4 border-b border-line pb-2 text-[11.5px] font-medium text-fg-3`}
        >
          <span>Session</span>
          <span className="hidden md:block">Mode</span>
          <span className="hidden md:block">Since start</span>
          <span className="hidden text-right md:block">Value</span>
          <span className="text-right">Today</span>
          <span className="hidden md:block">Holds</span>
          <span className="hidden md:block">Next</span>
        </div>
        {SESSIONS.map((s) => {
          const st = strategyById(s.strategyId);
          const { w, since } = sessionValues(s);
          return (
            <Link
              key={s.id}
              to={`/c/sessions/${s.id}`}
              className={`grid ${COLS} items-center gap-4 border-b border-line py-3 hover:bg-panel/70 ${s.stoppedOn ? 'opacity-60' : ''}`}
            >
              <span className="min-w-0">
                <span className="block truncate text-[14.5px] font-medium text-fg">{st?.name}</span>
                <span className="block truncate text-[12.5px] text-fg-3">
                  v{s.version} · started {s.started}
                  {s.stoppedOn ? ` · stopped ${s.stoppedOn}` : ''}
                </span>
              </span>
              <span className="hidden md:block">
                <ModeTag mode={s.mode} />
              </span>
              <span className="hidden items-center gap-2 md:flex">
                <Spark values={w.main} bench={w.bench} width={72} height={24} />
                <Delta v={since} className="text-[12px]">
                  {pts(since * 100)}
                </Delta>
              </span>
              <span className="hidden text-right font-mono text-[13.5px] tabular-nums text-fg md:block">
                {usd(s.value)}
              </span>
              <span className="text-right">
                <Delta v={s.today} className="text-[13.5px]">
                  {s.stoppedOn ? '' : signedUsd(s.today)}
                </Delta>
              </span>
              <span className="hidden min-w-0 md:block">
                <HoldsBar s={s} />
              </span>
              <span className="hidden truncate text-[12.5px] text-fg-2 md:block">
                {s.next ?? 'Stopped'}
              </span>
            </Link>
          );
        })}
      </Panel>
      <Foot
        items={['Sessions trade on your Alpaca account', 'paper sessions use its paper account']}
      />
    </Page>
  );
}

export function SessionPage() {
  const { id = '' } = useParams();
  const { ask } = useAsk();
  const s = SESSIONS.find((x) => x.id === id);
  const st = s ? strategyById(s.strategyId) : undefined;
  if (!s || !st)
    return (
      <Page>
        <p className="text-fg-2">This session could not be found.</p>
      </Page>
    );
  const { w, first, since } = sessionValues(s);
  const spySince = w.bench[w.bench.length - 1];
  return (
    <Page ask={{ context: st.id, placeholder: `Ask about the ${st.name} session` }} art="live">
      <PageHead
        eyebrow={
          <>
            <Link to="/c/sessions" className="hover:text-fg">
              Sessions
            </Link>{' '}
            / {s.mode}
          </>
        }
        title={st.name}
        meta={`Version ${s.version} · started ${s.started}${s.stoppedOn ? ` · stopped ${s.stoppedOn}` : ''} · ${s.next ?? 'not trading'}`}
        right={
          <>
            {!s.stoppedOn && <Button size="md">Pause</Button>}
            {!s.stoppedOn ? (
              <Button size="md">Stop</Button>
            ) : (
              <Button size="md" variant="primary">
                Restart
              </Button>
            )}
            <LinkButton to={`/c/strategies/${st.id}`} size="md">
              Open strategy
            </LinkButton>
          </>
        }
      />
      <Panel className="p-5 md:p-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Label>Session value</Label>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-3">
              <span className="font-mono text-[34px] font-medium leading-none tracking-[-0.04em] tabular-nums text-fg">
                {usd(s.value)}
              </span>
              {!s.stoppedOn && (
                <Delta v={s.today} className="text-[14px]">
                  {signedUsd(s.today)} today
                </Delta>
              )}
            </div>
          </div>
          <ModeTag mode={s.mode} />
        </div>
        <div className="mt-5">
          <Figures>
            <Figure label="Since start" sub={`SPY ${pts(spySince)}`}>
              <span className={tone(since)}>{pts(since * 100)}</span>
            </Figure>
            <Figure label="Gain" sub={`from ${usd(first)}`}>
              {signedUsd(s.value - first)}
            </Figure>
            <Figure label="Holdings" sub={s.holds.map((h) => h.symbol).join(' ') || 'cash'}>
              {s.holds.length}
            </Figure>
          </Figures>
        </div>
        <div className="mt-6">
          <PerfChart w={w} height={240} mainLabel="Session" />
        </div>
      </Panel>
      <div className="mt-14 grid gap-12 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div>
          <SectionHead
            title="Holdings"
            meta={s.holds.length ? 'Weights at the last price' : 'All cash'}
          />
          <div className="border-t border-line">
            {s.holds.map((h) => {
              const t = FUND_TODAY[h.symbol] ?? 0;
              return (
                <div
                  key={h.symbol}
                  className="grid grid-cols-[52px_minmax(0,1fr)_80px_96px_64px] items-center gap-3 border-b border-line py-2.5 text-[13px]"
                >
                  <span className="font-mono font-medium text-fg">{h.symbol}</span>
                  <span className="truncate text-fg-3">{FUND_NAME[h.symbol]}</span>
                  <span className="flex items-center gap-2">
                    <span className="block h-[5px] w-10 overflow-hidden rounded-full bg-sunk">
                      <i className="block h-full bg-fg" style={{ width: `${h.weight}%` }} />
                    </span>
                    <span className="font-mono text-[11.5px] tabular-nums text-fg-2">
                      {h.weight.toFixed(0)}%
                    </span>
                  </span>
                  <span className="text-right font-mono tabular-nums text-fg">
                    {usd((s.value * h.weight) / 100)}
                  </span>
                  <Delta v={t} className="text-right text-[12px]">
                    {pts2(t)}
                  </Delta>
                </div>
              );
            })}
          </div>
        </div>
        <div>
          <SectionHead title="Activity" meta="Newest first" />
          <div className="border-t border-line">
            {sessionActivity(s).map((a, i) => (
              <div
                key={i}
                className="grid grid-cols-[56px_minmax(0,1fr)] gap-3 border-b border-line py-2.5"
              >
                <span className="font-mono text-[12px] text-fg-3">{a.when}</span>
                <span className="min-w-0">
                  <span className="block text-[13px] text-fg">{a.what}</span>
                  <span className="block truncate text-[12px] text-fg-3">{a.detail}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-14">
        <SectionHead
          title="What it holds and why"
          meta="The outline with today's path in ink"
          right={
            <Button
              variant="quiet"
              onClick={() => ask(`Why does ${st.name} hold this today?`, st.id)}
            >
              Ask
            </Button>
          }
        />
        <div className="rounded-[10px] border border-line">
          <OutlineView strategy={st} items={itemsOf(st.name, st.cadence, st.rules)} />
        </div>
      </div>
      <Foot
        items={[
          `Version ${s.version}`,
          `started ${s.started}`,
          'values before Nov 19 are sample data',
        ]}
      />
    </Page>
  );
}
