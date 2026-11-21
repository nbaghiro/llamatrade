import { useState } from 'react';

import { ACCOUNT, pct, signedUsd, usd } from '../data';

import { AskLine } from './ask';
import { PerfChart } from './chart';
import { Page } from './frame';
import { StrategyLedger, LedgerHead } from './ledger';
import {
  accountWindow,
  dayLabel,
  drawdown,
  RANGES,
  RESTING,
  RUNNING,
  pts,
  tone,
  type Range,
} from './model';
import { Delta, Figure, Figures, Foot, Label, Panel, SectionHead, Segmented } from './ui';

/** The account against SPY in a lifted panel: total, range tabs, a three-up strip and the chart. */
export function AccountPanel({ title = 'Account against SPY' }: { title?: string }) {
  const [range, setRange] = useState<Range>('3M');
  const w = accountWindow(range);
  const n = w.main.length;
  const ea = w.main[n - 1];
  const eb = w.bench[n - 1];
  const dd = Math.min(...drawdown(w.main));
  const ddb = Math.min(...drawdown(w.bench));
  return (
    <Panel className="p-5 md:p-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Label>{title}</Label>
          <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="font-mono text-[34px] font-medium leading-none tracking-[-0.04em] tabular-nums text-fg md:text-[40px]">
              {usd(ACCOUNT.total)}
            </span>
            <Delta v={ACCOUNT.today} className="text-[14px]">
              {signedUsd(ACCOUNT.today)} ({pct(ACCOUNT.today / (ACCOUNT.total - ACCOUNT.today), 2)})
              today
            </Delta>
          </div>
          <div className="mt-2 text-[12.5px] text-fg-3">
            Live {usd(ACCOUNT.live)} · Paper {usd(ACCOUNT.paper)} · benchmark SPY
          </div>
        </div>
        <Segmented
          label="Range"
          value={range}
          onChange={setRange}
          options={RANGES.map((r) => ({ key: r, label: r }))}
        />
      </div>
      <div className="mt-5">
        <Figures>
          <Figure label={`Return, ${range}`} sub={`SPY ${pts(eb)}`}>
            <span className={tone(ea)}>{pts(ea)}</span>
          </Figure>
          <Figure label="Against SPY" sub={ea >= eb ? 'Ahead' : 'Behind'}>
            {`${ea - eb >= 0 ? '+' : '−'}${Math.abs(ea - eb).toFixed(1)}`}
          </Figure>
          <Figure label="Max drawdown" sub={`SPY ${pts(ddb)}`}>
            {pts(dd)}
          </Figure>
        </Figures>
      </div>
      <div className="mt-6">
        <PerfChart w={w} height={280} />
      </div>
      {w.markers.length > 0 && (
        <ol className="m-0 mt-4 flex list-none flex-wrap gap-x-5 gap-y-1.5 p-0 text-[12px] text-fg-2">
          {w.markers.map((m) => (
            <li key={m.n} className="inline-flex items-center gap-2">
              <i className="grid h-4 w-4 place-items-center rounded-[3px] border border-line-strong font-mono text-[9.5px] not-italic text-fg">
                {m.n}
              </i>
              <span className="font-mono text-[11px] text-fg-3">{dayLabel(w.dates[m.i])}</span>
              {m.label}
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

export function Today() {
  return (
    <Page ask={false}>
      <div className="mx-auto max-w-[820px] pb-10 pt-6 md:pt-12">
        <span className="text-[11.5px] font-medium text-fg-3">Friday, November 20 · 12:04 ET</span>
        <h1 className="m-0 mb-5 mt-1 text-[26px] font-semibold tracking-[-0.025em] text-fg md:text-[30px]">
          Today
        </h1>
        <AskLine
          size="lg"
          suggestions={[
            'Why is the account down today?',
            "Lower Recession Radar's gold to 30%",
            'Draft a trend strategy on QQQ',
          ]}
        />
      </div>
      <AccountPanel />
      <div className="mt-14">
        <SectionHead
          title="Strategies and sessions"
          meta={`${RUNNING.length} running · ${RESTING.length} not running · open a row for its outline`}
        />
        <LedgerHead />
        <StrategyLedger rows={RUNNING} initiallyOpen="recession-radar" />
        <div className="mb-0 mt-6 border-b border-line pb-2 text-[11.5px] font-medium text-fg-3">
          Not running
        </div>
        <StrategyLedger rows={RESTING} />
      </div>
      <Foot
        items={[
          'Prices Nov 20, 2026, 12:04 ET',
          'paper and live trading on Alpaca',
          'history before Nov 12 is sample data',
        ]}
      />
    </Page>
  );
}
