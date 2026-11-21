import { Link, useParams } from 'react-router-dom';

import { BACKTESTS, strategyById } from '../data';

import { useAsk } from './askContext';
import { PerfChart } from './chart';
import { Page, PageHead } from './frame';
import { backtestWindow, drawdown, pts, tone, type Window } from './model';
import { OutlineView } from './outline';
import { itemsOf } from './outlineModel';
import { Button, Figure, Figures, Foot, Label, LinkButton, SectionHead, Spark } from './ui';

const COLS =
  'grid-cols-[minmax(0,1fr)_80px] md:grid-cols-[minmax(0,1fr)_150px_96px_80px_110px_70px]';

export function BacktestsList() {
  const { ask } = useAsk();
  return (
    <Page placeholder="Ask about a backtest, or what to test next" art="backtest">
      <PageHead
        eyebrow="Nov 20, 2026 · 12:04 ET"
        title="Backtests"
        meta={`${BACKTESTS.length} runs · two years each · benchmark SPY`}
        right={
          <Button variant="primary" onClick={() => ask('Draft a trend strategy on QQQ')}>
            New backtest
          </Button>
        }
      />
      <div>
        <div
          className={`grid ${COLS} gap-4 border-b border-line pb-2 text-[11.5px] font-medium text-fg-3`}
        >
          <span>Strategy</span>
          <span className="hidden md:block">Against SPY</span>
          <span className="text-right">Return</span>
          <span className="hidden text-right md:block">SPY</span>
          <span className="hidden text-right md:block">Max drawdown</span>
          <span className="hidden text-right md:block">Sharpe</span>
        </div>
        {BACKTESTS.map((b) => {
          const s = strategyById(b.strategyId);
          const w = backtestWindow(b);
          return (
            <Link
              key={b.id}
              to={`/d/backtests/${b.id}`}
              className={`grid ${COLS} items-center gap-4 border-b border-line py-3 hover:bg-panel/70`}
            >
              <span className="min-w-0">
                <span className="block truncate text-[14.5px] font-medium text-fg">{s?.name}</span>
                <span className="block truncate text-[12.5px] text-fg-3">
                  v{b.version} · {b.range} · ran {b.ran}
                </span>
              </span>
              <span className="hidden md:block">
                <Spark values={w.main} bench={w.bench} width={140} height={28} toneBy={false} />
              </span>
              <span className={`text-right font-mono text-[14px] tabular-nums ${tone(b.ret)}`}>
                {pts(b.ret * 100)}
              </span>
              <span className="hidden text-right font-mono text-[13px] tabular-nums text-fg-3 md:block">
                {pts(b.spy * 100)}
              </span>
              <span className="hidden text-right font-mono text-[13px] tabular-nums text-fg-2 md:block">
                {pts(b.worst * 100)}
              </span>
              <span className="hidden text-right font-mono text-[13px] tabular-nums text-fg-2 md:block">
                {b.sharpe.toFixed(2)}
              </span>
            </Link>
          );
        })}
      </div>
      <Foot
        items={[
          'Backtests replay history with the same engine that runs sessions',
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
      <Page>
        <p className="text-fg-2">This backtest could not be found.</p>
      </Page>
    );
  const w = backtestWindow(b);
  const spyDd = Math.min(...drawdown(w.bench));
  return (
    <Page
      context={`backtest:${b.id}`}
      placeholder={`Ask about this run of ${s.name}`}
      art="backtest"
    >
      <PageHead
        eyebrow={
          <>
            <Link to="/d/backtests" className="hover:text-fg">
              Backtests
            </Link>{' '}
            / ran {b.ran}
          </>
        }
        title={`${s.name}, version ${b.version}`}
        meta={`${b.range} · $25,000 · benchmark SPY`}
        right={
          <>
            <Button variant="primary" size="md">
              Start paper session
            </Button>
            <LinkButton to={`/d/strategies/${s.id}`} size="md">
              Open in builder
            </LinkButton>
          </>
        }
      />
      <div className="border-t border-line pt-6">
        <Label>Backtest result</Label>
        <div className="mt-3">
          <Figures cols={4}>
            <Figure label="Total return" sub={`SPY ${pts(b.spy * 100)}`}>
              <span className={tone(b.ret)}>{pts(b.ret * 100)}</span>
            </Figure>
            <Figure label="Sharpe" sub="SPY 0.77">
              {b.sharpe.toFixed(2)}
            </Figure>
            <Figure label="Max drawdown" sub={`SPY ${pts(spyDd)}`}>
              {pts(b.worst * 100)}
            </Figure>
            <Figure label="Ending value" sub="from $25,000">
              ${Math.round(25000 * (1 + b.ret)).toLocaleString('en-US')}
            </Figure>
          </Figures>
        </div>
        <div className="mt-6">
          <PerfChart w={w} height={280} mainLabel={s.name} worst={b.worst * 100} />
        </div>
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
          <span className="text-[11.5px] text-fg-3">
            Sample run for the playground · past results do not predict future returns
          </span>
          <Button variant="quiet" onClick={() => ask(`Explain this backtest of ${s.name}`, s.id)}>
            Ask about this run
          </Button>
        </div>
      </div>
      <div className="mt-14">
        <SectionHead
          title="Monthly returns"
          meta="Each month's change, end of month to end of month"
        />
        <Monthly w={w} />
      </div>
      <div className="mt-14">
        <SectionHead title={`Outline at version ${b.version}`} meta={s.summary} />
        <div className="border-y border-line">
          <OutlineView strategy={s} items={itemsOf(s.name, s.cadence, s.rules)} />
        </div>
      </div>
      <Foot items={[`Ran ${b.ran}`, b.range, "past results don't predict future returns"]} />
    </Page>
  );
}
