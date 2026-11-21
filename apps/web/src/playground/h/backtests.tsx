import { Link, useParams } from 'react-router-dom';

import { BACKTESTS, backtestsFor, strategyById, type Backtest } from '../data';

import { useAsk } from './askContext';
import { Briefs, Stat } from './briefs';
import { PerfChart } from './chart';
import { Dateline, Lead, Page } from './frame';
import { backtestWindow, drawdown, pts, tone, type Window } from './model';
import { OutlineView } from './outline';
import { itemsOf } from './outlineModel';
import { FluidSpark } from './stories';
import { Button, Cell, Columns, Head, Kicker, LinkButton, Mono, Spread, TextLink } from './ui';

const gapOf = (b: Backtest) => (b.ret - b.spy) * 100;
const gapWords = (b: Backtest) =>
  `${Math.abs(gapOf(b)).toFixed(1)} points ${gapOf(b) >= 0 ? 'ahead of' : 'behind'} SPY`;

function RunStory({ b }: { b: Backtest }) {
  const { ask } = useAsk();
  const s = strategyById(b.strategyId);
  const w = backtestWindow(b);
  return (
    <Cell>
      <div className="flex items-center justify-between gap-3">
        <Mono className="text-fg-3">
          v{b.version} · ran {b.ran}
        </Mono>
        <span className="text-[11.5px] text-fg-3">Sharpe {b.sharpe.toFixed(2)}</span>
      </div>
      <Link to={`/h/backtests/${b.id}`} className="mt-3 block hover:underline">
        <Head size={21}>{s?.name}</Head>
      </Link>
      <div className="mt-4">
        <span
          className={`font-mono text-[28px] leading-none tracking-[-0.04em] tabular-nums ${tone(b.ret)}`}
        >
          {pts(b.ret * 100)}
        </span>
        <div className="mt-1.5 font-mono text-[11.5px] tabular-nums text-fg-3">
          SPY {pts(b.spy * 100)} · worst {pts(b.worst * 100)}
        </div>
      </div>
      <div className="mt-4">
        <FluidSpark w={w} height={40} toneBy={false} />
      </div>
      <p className="m-0 mt-3 text-[13px] text-fg-2">{gapWords(b)}.</p>
      <div className="mt-3 flex gap-5">
        <TextLink onClick={() => ask(`Explain this backtest of ${s?.name}`, b.strategyId)}>
          Ask about it
        </TextLink>
        <TextLink to={`/h/backtests/${b.id}`}>Open</TextLink>
      </div>
    </Cell>
  );
}

export function BacktestsList() {
  const { ask } = useAsk();
  const bestSharpe = [...BACKTESTS].sort((a, b) => b.sharpe - a.sharpe)[0];
  const ahead = BACKTESTS.filter((b) => b.ret > b.spy).length;
  return (
    <Page ask={{ placeholder: 'Ask about a backtest, or what to test next' }}>
      <Lead
        kicker={`Backtests · ${BACKTESTS.length} runs · two years each`}
        headline={`${ahead} of ${BACKTESTS.length} runs beat SPY, ${strategyById(bestSharpe.strategyId)?.name} has the best Sharpe`}
        deck="Every run replays history with the engine that runs sessions."
        right={
          <Button variant="primary" onClick={() => ask('Draft a trend strategy on QQQ')}>
            New backtest
          </Button>
        }
      />
      <Spread
        main={
          <>
            <Kicker right="newest first">Runs</Kicker>
            <Columns cols={3}>
              {BACKTESTS.map((b) => (
                <RunStory key={b.id} b={b} />
              ))}
            </Columns>
          </>
        }
        aside={
          <>
            <Briefs
              title="Against SPY"
              right="return minus SPY"
              items={[...BACKTESTS]
                .sort((a, b) => gapOf(b) - gapOf(a))
                .map((b) => ({
                  when: `${gapOf(b) >= 0 ? '+' : '−'}${Math.abs(gapOf(b)).toFixed(1)}`,
                  title: strategyById(b.strategyId)?.name ?? '',
                  detail: `v${b.version} · ${b.range}`,
                  to: `/h/backtests/${b.id}`,
                  tone: gapOf(b) >= 0 ? 'gain' : undefined,
                }))}
            />
            <Briefs
              title="Smallest drop"
              items={[...BACKTESTS]
                .sort((a, b) => b.worst - a.worst)
                .slice(0, 3)
                .map((b) => ({
                  when: pts(b.worst * 100),
                  title: strategyById(b.strategyId)?.name ?? '',
                  detail: `Sharpe ${b.sharpe.toFixed(2)}`,
                  to: `/h/backtests/${b.id}`,
                }))}
            />
          </>
        }
      />
      <Dateline
        items={[
          '$25,000 starting value',
          'benchmark SPY',
          "past results don't predict future returns",
        ]}
      />
    </Page>
  );
}

const MON = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];

function Monthly({ w }: { w: Window }) {
  const byMonth = new Map<string, { y: number; m: number; first: number; last: number }>();
  w.dates.forEach((d, i) => {
    const k = `${d.getUTCFullYear()}-${d.getUTCMonth()}`;
    const prev = i > 0 ? w.main[i - 1] : w.main[0];
    const cur = byMonth.get(k);
    if (cur) cur.last = w.main[i];
    else
      byMonth.set(k, { y: d.getUTCFullYear(), m: d.getUTCMonth(), first: prev, last: w.main[i] });
  });
  const ret = (a: number, b: number) => ((1 + b / 100) / (1 + a / 100) - 1) * 100;
  const years = [...new Set([...byMonth.values()].map((v) => v.y))];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse font-mono text-[11.5px] tabular-nums">
        <thead>
          <tr className="text-fg-3">
            <th className="w-14 py-1.5 text-left font-normal" />
            {MON.map((m, i) => (
              <th key={i} className="py-1.5 font-normal">
                {m}
              </th>
            ))}
            <th className="py-1.5 text-right font-normal">Year</th>
          </tr>
        </thead>
        <tbody>
          {years.map((y) => {
            const ms = [...byMonth.values()].filter((v) => v.y === y);
            const yr = ms.length ? ret(ms[0].first, ms[ms.length - 1].last) : 0;
            return (
              <tr key={y} className="border-t border-line">
                <td className="py-1.5 text-fg-3">{y}</td>
                {MON.map((_, m) => {
                  const v = ms.find((x) => x.m === m);
                  if (!v) return <td key={m} className="p-0.5" />;
                  const r = ret(v.first, v.last);
                  const k = Math.min(1, Math.abs(r) / 6);
                  return (
                    <td key={m} className="p-0.5">
                      <span
                        className={`block rounded-[4px] py-1.5 text-center ${r >= 0 ? 'text-gain' : 'text-loss'}`}
                        style={{
                          background: `color-mix(in srgb, rgb(var(${r >= 0 ? '--gain' : '--loss'})) ${Math.round(6 + k * 22)}%, transparent)`,
                        }}
                      >
                        {r >= 0 ? '+' : '−'}
                        {Math.abs(r).toFixed(1)}
                      </span>
                    </td>
                  );
                })}
                <td className={`py-1.5 text-right ${tone(yr)}`}>{pts(yr)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function BacktestPage() {
  const { id = '' } = useParams();
  const { ask } = useAsk();
  const b = BACKTESTS.find((x) => x.id === id);
  const s = b ? strategyById(b.strategyId) : undefined;
  if (!b || !s)
    return (
      <Page ask={{}}>
        <p className="text-fg-2">This backtest could not be found.</p>
      </Page>
    );
  const w = backtestWindow(b);
  const spyDd = Math.min(...drawdown(w.bench));
  const others = backtestsFor(s.id).filter((x) => x.id !== b.id);
  return (
    <Page ask={{ context: s.id, placeholder: `Ask about this run of ${s.name}` }}>
      <Lead
        kicker={
          <>
            <Link to="/h/backtests" className="hover:text-fg">
              Backtests
            </Link>{' '}
            · {s.name} v{b.version} · ran {b.ran}
          </>
        }
        headline={`Returned ${pts(b.ret * 100).replace('+', '')}, ${gapWords(b)}`}
        deck={`${b.range}, from $25,000. Worst drop ${pts(b.worst * 100)}.`}
        right={
          <>
            <Button variant="primary" size="md">
              Start paper session
            </Button>
            <LinkButton to={`/h/strategies/${s.id}`} size="md">
              Open in builder
            </LinkButton>
          </>
        }
      />
      <Spread
        main={
          <>
            <Kicker right="weekly, from the start">{s.name} against SPY</Kicker>
            <div className="mt-5">
              <PerfChart w={w} height={280} mainLabel={s.name} worst={b.worst * 100} />
            </div>
            <div className="mt-14">
              <Kicker right="end of month to end of month">Monthly returns</Kicker>
              <div className="mt-2">
                <Monthly w={w} />
              </div>
            </div>
            <div className="mt-14">
              <Kicker right={s.summary}>Outline at version {b.version}</Kicker>
              <div className="mt-1 overflow-x-auto border-b border-line">
                <OutlineView strategy={s} items={itemsOf(s.name, s.cadence, s.rules)} />
              </div>
            </div>
          </>
        }
        aside={
          <>
            <section className="mb-9">
              <Kicker>Result</Kicker>
              <Stat label="Total return" sub={`SPY ${pts(b.spy * 100)}`}>
                <span className={tone(b.ret)}>{pts(b.ret * 100)}</span>
              </Stat>
              <Stat label="Max drawdown" sub={`SPY ${pts(spyDd)}`}>
                {pts(b.worst * 100)}
              </Stat>
              <Stat label="Sharpe" sub="SPY 0.77">
                {b.sharpe.toFixed(2)}
              </Stat>
              <Stat label="Ending value" sub="from $25,000">
                ${Math.round(25000 * (1 + b.ret)).toLocaleString('en-US')}
              </Stat>
              <div className="mt-3">
                <TextLink onClick={() => ask(`Explain this backtest of ${s.name}`, s.id)}>
                  Ask about this run
                </TextLink>
              </div>
            </section>
            <Briefs
              title="Other runs"
              empty="This is the only run of this strategy."
              items={others.map((x) => ({
                when: x.ran,
                title: `v${x.version} · ${pts(x.ret * 100)}`,
                detail: x.range,
                to: `/h/backtests/${x.id}`,
              }))}
            />
          </>
        }
      />
      <Dateline
        items={[
          `Ran ${b.ran}`,
          b.range,
          'sample run for the playground',
          "past results don't predict future returns",
        ]}
      />
    </Page>
  );
}
