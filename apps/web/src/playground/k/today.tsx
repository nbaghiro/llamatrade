import { useState } from 'react';

import { ACCOUNT, pct, SESSIONS, signedUsd, strategyById, usd } from '../data';

import { PerfChart } from './chart';
import {
  accountWindow,
  dayLabel,
  drawdown,
  RANGES,
  pts,
  sessionWindow,
  tone,
  type Range,
} from './model';
import {
  Delta,
  Figure,
  Figures,
  LeftHead,
  ListLabel,
  ModeTag,
  PanelFoot,
  PanelHead,
  PickRow,
  Segmented,
  Spark,
  StageCard,
} from './ui';

const RUNNING_SESSIONS = SESSIONS.filter((s) => !s.stoppedOn);

/** The whole account against SPY, set like the example backtest on the sign-in screen. */
export function AccountPanel({ eyebrow = 'Whole account' }: { eyebrow?: string }) {
  const [range, setRange] = useState<Range>('3M');
  const w = accountWindow(range);
  const n = w.main.length;
  const ea = w.main[n - 1];
  const eb = w.bench[n - 1];
  const dd = Math.min(...drawdown(w.main));
  const ddb = Math.min(...drawdown(w.bench));
  return (
    <StageCard>
      <PanelHead
        eyebrow={eyebrow}
        title="Account against SPY"
        meta={`${dayLabel(w.dates[0])} to ${dayLabel(w.dates[n - 1])}, 2026 · live and paper · benchmark SPY`}
        right={
          <Segmented
            label="Range"
            value={range}
            onChange={setRange}
            options={RANGES.map((r) => ({ key: r, label: r }))}
          />
        }
      />
      <div className="mt-[18px]">
        <Figures>
          <Figure label={`Return, ${range}`} sub={`SPY ${pts(eb)}`}>
            <span className={tone(ea)}>{pts(ea)}</span>
          </Figure>
          <Figure label="Against SPY" sub={ea >= eb ? 'Ahead of SPY' : 'Behind SPY'}>
            {`${ea - eb >= 0 ? '+' : '−'}${Math.abs(ea - eb).toFixed(1)} pts`}
          </Figure>
          <Figure label="Max drawdown" sub={`SPY ${pts(ddb)}`}>
            {pts(dd)}
          </Figure>
        </Figures>
      </div>
      <div className="mt-[18px]">
        <PerfChart w={w} height={240} />
      </div>
      {w.markers.length > 0 && (
        <ol className="m-0 mt-4 grid list-none gap-x-5 gap-y-1.5 p-0 text-[12px] text-fg-2 sm:grid-cols-2">
          {w.markers.map((m) => (
            <li key={m.n} className="flex min-w-0 items-center gap-2">
              <i className="grid h-4 w-4 flex-none place-items-center rounded-[3px] border border-line-strong font-mono text-[9.5px] not-italic text-fg">
                {m.n}
              </i>
              <span className="font-mono text-[11px] text-fg-3">{dayLabel(w.dates[m.i])}</span>
              <span className="truncate">{m.label}</span>
            </li>
          ))}
        </ol>
      )}
      <PanelFoot note="History before Nov 12 is sample data. Past results don't predict future returns." />
    </StageCard>
  );
}

export function TodayLeft({ sel }: { sel: string }) {
  const stopped = SESSIONS.filter((s) => s.stoppedOn);
  return (
    <>
      <LeftHead
        eyebrow="Friday, November 20 · 12:04 ET"
        title="Good afternoon, Naib"
        sub={`${RUNNING_SESSIONS.length} sessions running. The market closes at 16:00 ET.`}
      />
      <div className="mt-7">
        <span className="text-[11.5px] font-medium text-fg-3">Account value</span>
        <div className="mt-1 font-mono text-[34px] font-medium leading-none tracking-[-0.04em] tabular-nums text-fg">
          {usd(ACCOUNT.total)}
        </div>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[12.5px]">
          <Delta v={ACCOUNT.today} className="text-[13px]">
            {signedUsd(ACCOUNT.today)} ({pct(ACCOUNT.today / (ACCOUNT.total - ACCOUNT.today), 2)})
            today
          </Delta>
          <span className="text-fg-3">
            Live {usd(ACCOUNT.live).replace(/\.\d+$/, '')} · Paper{' '}
            {usd(ACCOUNT.paper).replace(/\.\d+$/, '')}
          </span>
        </div>
      </div>
      <ListLabel right={<span className="font-mono tabular-nums">Today</span>}>Overview</ListLabel>
      <PickRow
        to="/k"
        on={sel === 'account'}
        title="Account against SPY"
        sub="All sessions, live and paper"
        right={
          <Delta v={ACCOUNT.today} className="text-[12.5px]">
            {pct(ACCOUNT.today / (ACCOUNT.total - ACCOUNT.today), 2)}
          </Delta>
        }
      />
      <ListLabel right={<span className="font-mono tabular-nums">Today</span>}>
        Running sessions
      </ListLabel>
      {RUNNING_SESSIONS.map((s) => {
        const st = strategyById(s.strategyId);
        return (
          <PickRow
            key={s.id}
            to={`/k?s=${s.id}`}
            on={sel === s.id}
            title={st?.name}
            sub={
              <span className="inline-flex items-center gap-2">
                <ModeTag mode={s.mode} />
                <span>{s.next}</span>
              </span>
            }
            right={
              <>
                <Spark values={sessionWindow(s).main.slice(-20)} width={52} height={20} />
                <Delta v={s.today} className="w-[74px] text-right text-[12.5px]">
                  {signedUsd(s.today).replace(/\.\d+$/, '')}
                </Delta>
              </>
            }
          />
        );
      })}
      {stopped.map((s) => (
        <PickRow
          key={s.id}
          to={`/k?s=${s.id}`}
          on={sel === s.id}
          muted
          title={strategyById(s.strategyId)?.name}
          sub={`Stopped ${s.stoppedOn} · ${usd(s.value).replace(/\.\d+$/, '')} in cash`}
        />
      ))}
      <ListLabel>What comes next</ListLabel>
      <ul className="m-0 grid list-none gap-2 p-0 pt-1.5 text-[12.5px]">
        <li className="grid grid-cols-[52px_minmax(0,1fr)] gap-3">
          <span className="font-mono text-[11.5px] text-fg-3">16:00</span>
          <span className="text-fg-2">Recession Radar checks SPY against its 200-day average</span>
        </li>
        <li className="grid grid-cols-[52px_minmax(0,1fr)] gap-3">
          <span className="font-mono text-[11.5px] text-fg-3">Nov 23</span>
          <span className="text-fg-2">Momentum Sectors rebalances</span>
        </li>
        <li className="grid grid-cols-[52px_minmax(0,1fr)] gap-3">
          <span className="font-mono text-[11.5px] text-fg-3">Dec 1</span>
          <span className="text-fg-2">All-Weather rebalances on live</span>
        </li>
      </ul>
    </>
  );
}
