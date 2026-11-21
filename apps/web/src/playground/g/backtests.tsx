import { useState } from 'react';

import { BACKTESTS, strategyById } from '../data';

import { PerfChart } from './chart';
import { backtestWindow, drawdown, pts, tone, type Window } from './model';
import { OutlineView } from './outline';
import { itemsOf } from './outlineModel';
import {
  Button,
  Figure,
  Figures,
  LeftHead,
  LinkButton,
  ListLabel,
  PanelFoot,
  PanelHead,
  PickRow,
  Segmented,
  Spark,
  StageCard,
} from './ui';

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
      <table className="w-full min-w-[560px] border-collapse font-mono text-[11.5px] tabular-nums">
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

type Tab = 'chart' | 'monthly' | 'outline';

/** One backtest on the stage, the same panel as the example on the sign-in screen. */
export function BacktestPanel({ id }: { id: string }) {
  const [tab, setTab] = useState<Tab>('chart');
  const b = BACKTESTS.find((x) => x.id === id);
  const s = b ? strategyById(b.strategyId) : undefined;
  if (!b || !s) return null;
  const w = backtestWindow(b);
  const spyDd = Math.min(...drawdown(w.bench));
  return (
    <StageCard>
      <PanelHead
        eyebrow={`Backtest · ran ${b.ran}`}
        title={`${s.name}, version ${b.version}`}
        meta={`${b.range} · $25,000 · benchmark SPY`}
        right={
          <Segmented
            label="Show"
            value={tab}
            onChange={setTab}
            options={[
              { key: 'chart', label: 'Chart' },
              { key: 'monthly', label: 'Monthly' },
              { key: 'outline', label: 'Outline' },
            ]}
          />
        }
      />
      <div className="mt-[18px]">
        <Figures>
          <Figure label="Total return" sub={`SPY ${pts(b.spy * 100)}`}>
            <span className={tone(b.ret)}>{pts(b.ret * 100)}</span>
          </Figure>
          <Figure label="Sharpe" sub="SPY 0.77">
            {b.sharpe.toFixed(2)}
          </Figure>
          <Figure label="Max drawdown" sub={`SPY ${pts(spyDd)}`}>
            {pts(b.worst * 100)}
          </Figure>
        </Figures>
      </div>
      <div className="mt-[18px] min-h-[300px]">
        {tab === 'chart' && (
          <PerfChart w={w} height={260} mainLabel={s.name} worst={b.worst * 100} />
        )}
        {tab === 'monthly' && <Monthly w={w} />}
        {tab === 'outline' && (
          <div className="-mx-5 border-y border-line md:-mx-7 md:px-2">
            <OutlineView strategy={s} items={itemsOf(s.name, s.cadence, s.rules)} />
          </div>
        )}
      </div>
      <PanelFoot note="A backtest replays history with the same engine that runs paper and live sessions. Past results don't predict future returns.">
        <LinkButton to={`/g/strategies/${s.id}`}>Open in builder</LinkButton>
        <Button variant="primary">Start paper session</Button>
      </PanelFoot>
    </StageCard>
  );
}

export function BacktestsLeft({ sel }: { sel: string }) {
  return (
    <>
      <LeftHead
        title="Backtests"
        sub={`${BACKTESTS.length} runs over two years each, against SPY.`}
      />
      <ListLabel right={<span>Return</span>}>Newest first</ListLabel>
      {BACKTESTS.map((b) => {
        const s = strategyById(b.strategyId);
        const w = backtestWindow(b);
        return (
          <PickRow
            key={b.id}
            to={`/g/backtests/${b.id}`}
            on={sel === b.id}
            title={s?.name}
            sub={`v${b.version} · ran ${b.ran} · worst ${pts(b.worst * 100)}`}
            right={
              <>
                <Spark values={w.main} bench={w.bench} width={52} height={20} toneBy={false} />
                <span
                  className={`w-[50px] text-right font-mono text-[12.5px] tabular-nums ${tone(b.ret)}`}
                >
                  {pts(b.ret * 100)}
                </span>
              </>
            }
          />
        );
      })}
    </>
  );
}
