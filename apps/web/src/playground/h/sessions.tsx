import { Link, useParams } from 'react-router-dom';

import { pct, SESSIONS, signedUsd, strategyById, usd, type Session } from '../data';

import { useAsk } from './askContext';
import { Briefs, Stat } from './briefs';
import { PerfChart } from './chart';
import { Dateline, Lead, Page } from './frame';
import { FUND_NAME, FUND_TODAY, pts, pts2, sessionActivity, sessionValues, tone } from './model';
import { OutlineView } from './outline';
import { itemsOf } from './outlineModel';
import { allActivity, driftBriefs, driftOf, rebalanceBriefs, RUNNING_SESSIONS } from './paper';
import { FluidSpark } from './stories';
import {
  Button,
  Cell,
  Columns,
  Delta,
  Head,
  Kicker,
  LinkButton,
  Mono,
  Spread,
  TextLink,
} from './ui';

const SHADES = ['bg-chart-1', 'bg-chart-2', 'bg-chart-3', 'bg-chart-4', 'bg-chart-5'];

function HoldsBar({ s }: { s: Session }) {
  if (!s.holds.length) return <span className="text-[12px] text-fg-3">All cash</span>;
  return (
    <span className="block">
      <span className="flex h-[5px] w-full overflow-hidden rounded-full bg-sunk">
        {s.holds.map((h, i) => (
          <i
            key={h.symbol}
            className={`block h-full ${SHADES[i % 5]}`}
            style={{ width: `${h.weight}%` }}
          />
        ))}
      </span>
      <span className="mt-1.5 block truncate font-mono text-[10.5px] text-fg-3">
        {s.holds.map((h) => `${h.symbol} ${h.weight.toFixed(0)}%`).join('  ')}
      </span>
    </span>
  );
}

function SessionStory({ s }: { s: Session }) {
  const { ask } = useAsk();
  const st = strategyById(s.strategyId);
  const { w, since } = sessionValues(s);
  return (
    <Cell className={s.stoppedOn ? 'opacity-70' : ''}>
      <div className="flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-1.5">
          <i
            aria-hidden="true"
            className={`h-1.5 w-1.5 rounded-full ${s.stoppedOn ? 'bg-fg-3' : s.mode === 'live' ? 'bg-gain' : 'border border-fg-3'}`}
          />
          <Mono className={s.stoppedOn ? 'text-fg-3' : 'text-fg'}>
            {s.stoppedOn ? `Stopped ${s.stoppedOn}` : s.mode} · v{s.version}
          </Mono>
        </span>
        <span className="text-[11.5px] text-fg-3">since {s.started}</span>
      </div>
      <Link to={`/h/sessions/${s.id}`} className="mt-3 block hover:underline">
        <Head size={22}>{st?.name}</Head>
      </Link>
      <div className="mt-4 font-mono text-[26px] leading-none tracking-[-0.04em] tabular-nums text-fg">
        {usd(s.value)}
      </div>
      <div className="mt-1.5 font-mono text-[11.5px] tabular-nums text-fg-3">
        {!s.stoppedOn && (
          <>
            <Delta v={s.today}>{signedUsd(s.today)}</Delta> today ·{' '}
          </>
        )}
        <span className={tone(since)}>{pts(since * 100)}</span> since start
      </div>
      <div className="mt-4">
        <FluidSpark w={w} height={40} />
      </div>
      <div className="mt-4">
        <HoldsBar s={s} />
      </div>
      {s.next && <p className="m-0 mt-3 text-[13px] text-fg-2">{s.next}</p>}
      <div className="mt-3 flex gap-5">
        <TextLink onClick={() => ask(`Why does ${st?.name} hold this today?`, s.strategyId)}>
          Ask about it
        </TextLink>
        <TextLink to={`/h/sessions/${s.id}`}>Open</TextLink>
      </div>
    </Cell>
  );
}

export function SessionsList() {
  const total = RUNNING_SESSIONS.reduce((a, s) => a + s.value, 0);
  const today = RUNNING_SESSIONS.reduce((a, s) => a + s.today, 0);
  const stopped = SESSIONS.filter((s) => s.stoppedOn);
  return (
    <Page ask={{ placeholder: 'Ask about your sessions' }}>
      <Lead
        kicker={`Sessions · ${RUNNING_SESSIONS.length} running · ${stopped.length} stopped`}
        headline={`${usd(total)} in running sessions, ${today < 0 ? 'down' : 'up'} ${usd(Math.abs(today))} today`}
        deck="Sessions trade on your Alpaca account, paper or live."
      />
      <Spread
        main={
          <>
            <Kicker right={`${RUNNING_SESSIONS.length} sessions`}>Running</Kicker>
            <Columns cols={3}>
              {RUNNING_SESSIONS.map((s) => (
                <SessionStory key={s.id} s={s} />
              ))}
            </Columns>
            <div className="mt-8">
              <Kicker ink={false}>Stopped</Kicker>
              <Columns cols={3}>
                {stopped.map((s) => (
                  <SessionStory key={s.id} s={s} />
                ))}
              </Columns>
            </div>
          </>
        }
        aside={
          <>
            <Briefs title="Drift" right="from target" items={driftBriefs()} />
            <Briefs title="Rebalances" items={rebalanceBriefs().slice(0, 4)} />
            <Briefs
              title="Activity"
              right="newest first"
              items={allActivity()
                .filter((a) => a.what !== 'Rebalanced')
                .slice(0, 6)
                .map((a) => ({
                  when: a.when,
                  title: a.what,
                  detail: `${a.name} · ${a.detail}`,
                  to: `/h/sessions/${a.session.id}`,
                }))}
            />
          </>
        }
      />
      <Dateline
        items={[
          'Paper sessions use the Alpaca paper account',
          'values before Nov 19 are sample data',
        ]}
      />
    </Page>
  );
}

function sessionHeadline(s: Session, name: string, since: number): string {
  const sinceWords = `${since >= 0 ? 'up' : 'down'} ${Math.abs(since * 100).toFixed(1)}% since ${s.started}`;
  if (s.stoppedOn) return `${name} stopped ${s.stoppedOn} at ${usd(s.value)}, ${sinceWords}`;
  return `${name} is ${s.today < 0 ? 'down' : 'up'} ${usd(Math.abs(s.today))} today, ${sinceWords}`;
}

export function SessionPage() {
  const { id = '' } = useParams();
  const { ask } = useAsk();
  const s = SESSIONS.find((x) => x.id === id);
  const st = s ? strategyById(s.strategyId) : undefined;
  if (!s || !st)
    return (
      <Page ask={{}}>
        <p className="text-fg-2">This session could not be found.</p>
      </Page>
    );
  const { w, first, since } = sessionValues(s);
  const spySince = w.bench[w.bench.length - 1];
  const drift = new Map(driftOf(s).map((d) => [d.symbol, d]));
  return (
    <Page ask={{ context: st.id, placeholder: `Ask about the ${st.name} session` }}>
      <Lead
        size={44}
        kicker={
          <>
            <Link to="/h/sessions" className="hover:text-fg">
              Sessions
            </Link>{' '}
            · {s.mode} · v{s.version} · started {s.started}
          </>
        }
        headline={sessionHeadline(s, st.name, since)}
        deck={s.next ? `${s.next}.` : 'Positions closed, all cash.'}
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
            <LinkButton to={`/h/strategies/${st.id}`} size="md">
              Open strategy
            </LinkButton>
          </>
        }
      />
      <Spread
        main={
          <>
            <Kicker right={`SPY ${pts(spySince)} over the same days`}>Session against SPY</Kicker>
            <div className="mt-5">
              <PerfChart w={w} height={260} mainLabel="Session" />
            </div>
            <div className="mt-14">
              <Kicker
                right={
                  <TextLink onClick={() => ask(`Why does ${st.name} hold this today?`, st.id)}>
                    Ask why
                  </TextLink>
                }
              >
                What it holds and why
              </Kicker>
              <div className="mt-1 overflow-x-auto border-b border-line">
                <OutlineView strategy={st} items={itemsOf(st.name, st.cadence, st.rules)} />
              </div>
            </div>
          </>
        }
        aside={
          <>
            <section className="mb-9">
              <Kicker right={s.mode}>Value</Kicker>
              <Stat label="Now">{usd(s.value)}</Stat>
              {!s.stoppedOn && (
                <Stat label="Today" sub={pct(s.today / (s.value - s.today), 2)}>
                  <span className={tone(s.today)}>{signedUsd(s.today)}</span>
                </Stat>
              )}
              <Stat label="Since start" sub={`SPY ${pts(spySince)}`}>
                <span className={tone(since)}>{pts(since * 100)}</span>
              </Stat>
              <Stat label="Gain" sub={`from ${usd(first)}`}>
                {signedUsd(s.value - first)}
              </Stat>
            </section>
            <section className="mb-9">
              <Kicker right="held · target">Holdings</Kicker>
              {s.holds.length === 0 && (
                <p className="m-0 py-3 text-[12.5px] text-fg-3">All cash.</p>
              )}
              {s.holds.map((h) => {
                const d = drift.get(h.symbol);
                return (
                  <div
                    key={h.symbol}
                    className="grid grid-cols-[46px_minmax(0,1fr)_auto] items-baseline gap-2 border-b border-line py-2.5 last:border-b-0"
                  >
                    <span className="font-mono text-[12.5px] font-medium text-fg">{h.symbol}</span>
                    <span className="min-w-0">
                      <span className="block truncate text-[12px] text-fg-3">
                        {FUND_NAME[h.symbol]}
                      </span>
                      <Delta v={FUND_TODAY[h.symbol] ?? 0} className="text-[11px]">
                        {pts2(FUND_TODAY[h.symbol] ?? 0)} today
                      </Delta>
                    </span>
                    <span className="text-right font-mono text-[12.5px] tabular-nums text-fg">
                      {h.weight.toFixed(1)}%
                      {d && (
                        <span className="block text-[11px] text-fg-3">
                          {d.target}% · {d.off >= 0 ? '+' : '−'}
                          {Math.abs(d.off).toFixed(1)}
                        </span>
                      )}
                    </span>
                  </div>
                );
              })}
            </section>
            <Briefs
              title="Activity"
              right="newest first"
              items={sessionActivity(s).map((a) => ({
                when: a.when,
                title: a.what,
                detail: a.detail,
              }))}
            />
          </>
        }
      />
      <Dateline
        items={[
          `Version ${s.version}`,
          `started ${s.started}`,
          'values before Nov 19 are sample data',
        ]}
      />
    </Page>
  );
}
