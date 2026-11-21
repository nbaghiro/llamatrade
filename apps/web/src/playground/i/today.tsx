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
import { ListCard } from './shell';
import {
  Delta,
  Figure,
  Figures,
  LinkButton,
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
export function AccountPanel({ greet = false }: { greet?: boolean }) {
  const [range, setRange] = useState<Range>('3M');
  const w = accountWindow(range);
  const n = w.main.length;
  const ea = w.main[n - 1];
  const eb = w.bench[n - 1];
  const dd = Math.min(...drawdown(w.main));
  const ddb = Math.min(...drawdown(w.bench));
  const segmented = (
    <Segmented
      label="Range"
      value={range}
      onChange={setRange}
      options={RANGES.map((r) => ({ key: r, label: r }))}
    />
  );
  return (
    <StageCard>
      {greet ? (
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
          <div className="min-w-0">
            <span className="text-[11px] font-medium text-fg-3">
              Good afternoon, Naib · Friday, November 20, 12:04 ET
            </span>
            <div className="mt-1.5 font-mono text-[34px] font-medium leading-none tracking-[-0.04em] tabular-nums text-fg">
              {usd(ACCOUNT.total)}
            </div>
            <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[12.5px]">
              <Delta v={ACCOUNT.today} className="text-[13px]">
                {signedUsd(ACCOUNT.today)} (
                {pct(ACCOUNT.today / (ACCOUNT.total - ACCOUNT.today), 2)}) today
              </Delta>
              <span className="text-fg-3">
                Live {usd(ACCOUNT.live).replace(/\.\d+$/, '')} · Paper{' '}
                {usd(ACCOUNT.paper).replace(/\.\d+$/, '')}
              </span>
            </div>
          </div>
          {segmented}
        </div>
      ) : (
        <PanelHead
          eyebrow="Portfolio"
          title="Account against SPY"
          meta={`${dayLabel(w.dates[0])} to ${dayLabel(w.dates[n - 1])}, 2026 · live and paper · benchmark SPY`}
          right={segmented}
        />
      )}
      {greet && (
        <div className="mt-6 flex flex-wrap items-baseline justify-between gap-x-3 pb-2">
          <span className="text-[13px] font-semibold text-fg">Account against SPY</span>
          <span className="text-[12px] text-fg-3">
            {dayLabel(w.dates[0])} to {dayLabel(w.dates[n - 1])}, 2026 · live and paper
          </span>
        </div>
      )}
      <div className={greet ? '' : 'mt-[18px]'}>
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
        <PerfChart w={w} height={230} />
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

const COMING_UP = [
  { when: '16:00', what: 'Recession Radar checks SPY against its 200-day average' },
  { when: 'Nov 23', what: 'Momentum Sectors rebalances' },
  { when: 'Dec 1', what: 'All-Weather rebalances on live' },
];

/** Under the Today card: the running sessions and what happens next. */
export function TodayBelow() {
  const stopped = SESSIONS.filter((s) => s.stoppedOn);
  return (
    <ListCard
      title="Running sessions"
      meta={`${RUNNING_SESSIONS.length} running on Alpaca. The market closes at 16:00 ET.`}
      right={<LinkButton to="/i/sessions">All sessions</LinkButton>}
    >
      <ListLabel right={<span className="font-mono tabular-nums">Today</span>}>
        Live and paper
      </ListLabel>
      {RUNNING_SESSIONS.map((s) => {
        const st = strategyById(s.strategyId);
        return (
          <PickRow
            key={s.id}
            to={`/i/sessions/${s.id}`}
            on={false}
            title={st?.name}
            sub={
              <span className="inline-flex items-center gap-2">
                <ModeTag mode={s.mode} />
                <span>{s.next}</span>
              </span>
            }
            right={
              <>
                <Spark values={sessionWindow(s).main.slice(-20)} width={72} height={22} />
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
          to={`/i/sessions/${s.id}`}
          on={false}
          muted
          title={strategyById(s.strategyId)?.name}
          sub={`Stopped ${s.stoppedOn} · ${usd(s.value).replace(/\.\d+$/, '')} in cash`}
        />
      ))}
      <ListLabel>Coming up</ListLabel>
      <ul className="m-0 grid list-none gap-2 p-0 pb-1 pt-1.5 text-[12.5px]">
        {COMING_UP.map((c) => (
          <li key={c.when} className="grid grid-cols-[56px_minmax(0,1fr)] gap-3">
            <span className="font-mono text-[11.5px] text-fg-3">{c.when}</span>
            <span className="text-fg-2">{c.what}</span>
          </li>
        ))}
      </ul>
    </ListCard>
  );
}
