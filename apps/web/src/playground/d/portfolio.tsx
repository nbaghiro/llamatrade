import { useState } from 'react';

import { ACCOUNT, pct, SAMPLE_FUND_RETURNS, signedUsd, strategyById, usd } from '../data';

import { PerfChart } from './chart';
import { Block, Page, PageHead } from './frame';
import {
  accountWindow,
  dayLabel,
  drawdown,
  FUND_NAME,
  FUND_TODAY,
  fundSpark,
  HOLDINGS,
  pts,
  pts2,
  RANGES,
  tone,
  type Range,
} from './model';
import { ClassBar, Delta, Figure, Figures, Foot, Label, Segmented, Spark } from './ui';

type Period = '1M' | '3M' | 'YTD' | '1Y';

/** The account against SPY, in full: total, range tabs, a three-up strip, the chart and its markers. */
function AccountFull() {
  const [range, setRange] = useState<Range>('3M');
  const w = accountWindow(range);
  const n = w.main.length;
  const ea = w.main[n - 1];
  const eb = w.bench[n - 1];
  const dd = Math.min(...drawdown(w.main));
  const ddb = Math.min(...drawdown(w.bench));
  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-4 pb-5">
        <div>
          <Label>Account against SPY</Label>
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
      <div className="mt-7">
        <PerfChart w={w} height={300} />
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
    </section>
  );
}

function Holdings() {
  const [period, setPeriod] = useState<Period>('1Y');
  return (
    <Block
      title="Holdings"
      meta="Each fund across every running session"
      right={
        <Segmented
          label="Period"
          value={period}
          onChange={setPeriod}
          options={(['1M', '3M', 'YTD', '1Y'] as const).map((p) => ({ key: p, label: p }))}
        />
      }
    >
      <div className="grid grid-cols-[56px_minmax(0,1fr)_90px] gap-3 border-b border-line pb-2 text-[11.5px] font-medium text-fg-3 md:grid-cols-[56px_minmax(0,1fr)_120px_72px_72px_120px_minmax(0,160px)]">
        <span>Fund</span>
        <span />
        <span className="hidden md:block">Past year</span>
        <span className="hidden text-right md:block">{period}</span>
        <span className="hidden text-right md:block">Today</span>
        <span className="text-right">Value</span>
        <span className="hidden md:block">Held by</span>
      </div>
      {HOLDINGS.map((h) => {
        const r = SAMPLE_FUND_RETURNS[h.symbol]?.[period] ?? 0;
        const t = FUND_TODAY[h.symbol] ?? 0;
        return (
          <div
            key={h.symbol}
            className="grid grid-cols-[56px_minmax(0,1fr)_90px] items-center gap-3 border-b border-line py-2.5 text-[13px] md:grid-cols-[56px_minmax(0,1fr)_120px_72px_72px_120px_minmax(0,160px)]"
          >
            <span className="font-mono font-medium text-fg">{h.symbol}</span>
            <span className="truncate text-fg-3">{FUND_NAME[h.symbol]}</span>
            <span className="hidden md:block">
              <Spark values={fundSpark(h.symbol)} width={110} height={24} />
            </span>
            <span className={`hidden text-right font-mono tabular-nums md:block ${tone(r)}`}>
              {pts2(r, 1)}
            </span>
            <Delta v={t} className="hidden text-right text-[12.5px] md:block">
              {pts2(t)}
            </Delta>
            <span className="text-right font-mono tabular-nums text-fg">{usd(h.value)}</span>
            <span className="hidden truncate text-[12px] text-fg-3 md:block">
              {h.sessions.map((id) => strategyById(id)?.name.split(' ')[0]).join(', ')}
              {h.live > 0 && h.paper > 0
                ? ' · live and paper'
                : h.live > 0
                  ? ' · live'
                  : ' · paper'}
            </span>
          </div>
        );
      })}
    </Block>
  );
}

export function Portfolio() {
  return (
    <Page context="portfolio" placeholder="Ask about the account, holdings or risk" art="own">
      <PageHead
        eyebrow="Nov 20, 2026 · 12:04 ET"
        title="Portfolio"
        meta={`${usd(ACCOUNT.total)} across live and paper · ${HOLDINGS.length} funds held`}
      />
      <AccountFull />
      <Block title="Asset classes" meta="What the account holds, by kind of fund, with cash">
        <ClassBar detail />
      </Block>
      <Holdings />
      <Foot items={['Prices Nov 20, 2026, 12:04 ET', 'fund returns and history are sample data']} />
    </Page>
  );
}
