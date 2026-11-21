import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { ACCOUNT, BACKTESTS, SAMPLE_SECTOR_RANKS, signedUsd, STRATEGIES, usd } from '../data';

import { Brief, Composer } from './ask';
import { useAsk } from './askContext';
import { PerfChart } from './chart';
import { Block } from './frame';
import { LedgerHead, StrategyLedger } from './ledger';
import {
  accountWindow,
  DRIFT,
  drawdown,
  money0,
  RANGES,
  RESTING,
  RUNNING,
  since,
  SPY_VS_200D,
  pts,
  pts2,
  tone,
  type Range,
} from './model';
import { Backdrop, Delta, Foot, ModeTag, Mono, Segmented } from './ui';

function Change({
  kind,
  figure,
  detail,
  prompt,
}: {
  kind: string;
  figure: ReactNode;
  detail: string;
  prompt: string;
}) {
  const { ask } = useAsk();
  return (
    <button
      type="button"
      onClick={() => ask(prompt)}
      className="group grid min-w-0 content-start gap-2 border-line py-5 text-left md:border-l md:px-6 md:first:border-l-0 md:first:pl-0 max-md:border-t max-md:[&:nth-child(-n+2)]:border-t-0 max-md:odd:pr-4 max-md:even:border-l max-md:even:pl-4"
    >
      <Mono className="text-fg-3">{kind}</Mono>
      <span className="font-mono text-[22px] leading-none tracking-[-0.03em] tabular-nums text-fg md:text-[26px]">
        {figure}
      </span>
      <span className="text-[12.5px] leading-snug text-fg-3">{detail}</span>
      <span className="text-[12px] text-fg-3 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
        Ask about this →
      </span>
    </button>
  );
}

function SinceLastLooked() {
  const s = since('2026-11-16');
  const vglt = DRIFT.find((d) => d.symbol === 'VGLT');
  const drift = vglt ? vglt.holds - vglt.target : 0;
  return (
    <Block
      className="mt-24"
      title="Since you last looked"
      meta="Monday, Nov 16 at 17:40 ET · select one to ask about it"
    >
      <div className="grid grid-cols-2 border-y border-line md:grid-cols-4">
        <Change
          kind="P&L"
          figure={<span className={tone(s.change)}>{signedUsd(s.change)}</span>}
          detail={`Account ${pts2(s.pct)}, SPY ${pts2(s.spy)}. Today ${signedUsd(ACCOUNT.today)}.`}
          prompt="Why is the account down today?"
        />
        <Change
          kind="Fills"
          figure="3 orders"
          detail="Momentum Sectors rebalanced on Nov 16 and kept XLC, XLF and XLI."
          prompt="What orders filled this week?"
        />
        <Change
          kind="Drift"
          figure={`${drift >= 0 ? '+' : '−'}${Math.abs(drift).toFixed(1)} pts`}
          detail="VGLT in All-Weather, over its 40% target."
          prompt="What has drifted from target?"
        />
        <Change
          kind="Signal"
          figure={pts2(SPY_VS_200D)}
          detail="SPY against its 200-day average. Recession Radar stays in TLT and GLD."
          prompt="Explain Recession Radar"
        />
      </div>
    </Block>
  );
}

const DAYS = [20, 23, 24, 25, 26, 27, 30, 1, 2, 3, 4];
type Glyph = 'ring' | 'dot' | 'square';

function Mark({ g, on = true }: { g: Glyph; on?: boolean }) {
  const c = on ? 'border-fg bg-fg' : 'border-fg-3 bg-fg-3';
  if (g === 'ring')
    return (
      <i aria-hidden="true" className="block h-[7px] w-[7px] rounded-full border border-fg-2" />
    );
  if (g === 'square') return <i aria-hidden="true" className={`block h-2 w-2 border ${c}`} />;
  return <i aria-hidden="true" className={`block h-2 w-2 rounded-full border ${c}`} />;
}

const NEXT: {
  day: number;
  when: string;
  in: string;
  name: string;
  id: string;
  what: string;
  mode: 'live' | 'paper';
  g: Glyph;
}[] = [
  {
    day: 20,
    when: 'Today 16:00',
    in: 'in 4 h',
    name: 'Recession Radar',
    id: 's-rr',
    what: `Checks SPY against its 200-day average at each close. SPY is ${pts2(SPY_VS_200D).slice(1)} under.`,
    mode: 'paper',
    g: 'ring',
  },
  {
    day: 23,
    when: 'Mon Nov 23',
    in: 'in 3 days',
    name: 'Momentum Sectors',
    id: 's-ms',
    what: `Weekly rebalance to the top three sectors. ${SAMPLE_SECTOR_RANKS.slice(0, 3)
      .map((r) => r.symbol)
      .join(', ')} lead on 90-day return.`,
    mode: 'paper',
    g: 'dot',
  },
  {
    day: 1,
    when: 'Tue Dec 1',
    in: 'in 11 days',
    name: 'All-Weather Portfolio',
    id: 's-aw',
    what: 'Monthly rebalance back to target weights. VGLT is 3.9 pts over.',
    mode: 'live',
    g: 'square',
  },
];

function UpNext() {
  return (
    <Block className="mt-20" title="Up next" meta="Rebalances and checks over the next two weeks">
      <div className="grid grid-cols-11 border-t border-line pt-3" aria-hidden="true">
        {DAYS.map((d, i) => (
          <div key={i} className="grid justify-items-start gap-2">
            <span
              className={`font-mono text-[10.5px] tabular-nums ${i === 0 ? 'text-fg' : 'text-fg-3'}`}
            >
              {i === 0 ? 'Nov 20' : d === 1 ? 'Dec 1' : d}
            </span>
            <span className="flex h-3 items-center gap-1">
              <Mark g="ring" />
              {(d === 23 || d === 30) && <Mark g="dot" />}
              {d === 1 && <Mark g="square" />}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-4 border-t border-line">
        {NEXT.map((n) => (
          <Link
            key={n.name}
            to={`/d/sessions/${n.id}`}
            className="grid grid-cols-[14px_96px_minmax(0,1fr)] items-baseline gap-4 border-b border-line py-3.5 transition-colors hover:bg-panel/60 md:grid-cols-[14px_110px_80px_190px_minmax(0,1fr)_64px]"
          >
            <span className="translate-y-[-1px] self-center">
              <Mark g={n.g} />
            </span>
            <span className="font-mono text-[12.5px] text-fg">{n.when}</span>
            <span className="hidden font-mono text-[11.5px] text-fg-3 md:block">{n.in}</span>
            <span className="truncate text-[14px] font-medium text-fg max-md:col-start-3 max-md:row-start-1">
              {n.name}
            </span>
            <span className="text-[13px] text-fg-3 max-md:col-span-2 max-md:col-start-2">
              {n.what}
            </span>
            <span className="hidden md:block">
              <ModeTag mode={n.mode} />
            </span>
          </Link>
        ))}
      </div>
    </Block>
  );
}

function AccountLine() {
  const [range, setRange] = useState<Range>('3M');
  const w = { ...accountWindow(range), markers: [] };
  const n = w.main.length;
  const ea = w.main[n - 1];
  const eb = w.bench[n - 1];
  const dd = Math.min(...drawdown(w.main));
  const rows: [string, ReactNode, string][] = [
    [
      `Return, ${range}`,
      <span key="r" className={tone(ea)}>
        {pts(ea)}
      </span>,
      `SPY ${pts(eb)}`,
    ],
    ['Against SPY', `${ea - eb >= 0 ? '+' : '−'}${Math.abs(ea - eb).toFixed(1)} pts`, ''],
    ['Max drawdown', pts(dd), `SPY ${pts(Math.min(...drawdown(w.bench)))}`],
  ];
  return (
    <Block
      className="mt-20"
      title="Account"
      meta="Live and paper together, against SPY"
      right={
        <Segmented
          label="Range"
          value={range}
          onChange={setRange}
          options={RANGES.map((r) => ({ key: r, label: r }))}
        />
      }
    >
      <div className="grid gap-x-12 gap-y-6 border-t border-line pt-6 md:grid-cols-[300px_minmax(0,1fr)]">
        <div>
          <div className="font-mono text-[34px] font-medium leading-none tracking-[-0.04em] tabular-nums text-fg">
            {usd(ACCOUNT.total)}
          </div>
          <Delta v={ACCOUNT.today} className="mt-2 block text-[13px]">
            {signedUsd(ACCOUNT.today)} today
          </Delta>
          <div className="mt-1 text-[12.5px] text-fg-3">
            Live {money0(ACCOUNT.live)} · Paper {money0(ACCOUNT.paper)}
          </div>
          <div className="mt-5 border-t border-line">
            {rows.map(([k, v, sub]) => (
              <div
                key={k}
                className="grid grid-cols-[minmax(0,1fr)_auto_72px] items-baseline gap-3 border-b border-line py-2 text-[13px]"
              >
                <span className="text-fg-3">{k}</span>
                <span className="font-mono tabular-nums text-fg">{v}</span>
                <span className="text-right font-mono text-[11.5px] tabular-nums text-fg-3">
                  {sub}
                </span>
              </div>
            ))}
          </div>
          <Link
            to="/d/portfolio"
            className="mt-3 inline-block text-[12.5px] text-fg-2 hover:text-fg"
          >
            Full chart and holdings →
          </Link>
        </div>
        <div className="min-w-0">
          <PerfChart w={w} height={210} drawdownStrip={false} legend={false} />
        </div>
      </div>
    </Block>
  );
}

export function Today() {
  const running = RUNNING.length;
  return (
    <div className="relative">
      <Backdrop hero height={620} />
      <div className="relative mx-auto max-w-[1120px] px-4 pb-32 md:px-10">
        <div className="pt-14 md:pt-24">
          <span className="font-mono text-[11px] text-fg-3">Friday, November 20 · 12:04 ET</span>
          <h1 className="m-0 mt-3 text-[34px] font-semibold leading-[1.05] tracking-[-0.035em] text-fg md:text-[48px]">
            Today
          </h1>
          <p className="m-0 mb-8 mt-3 text-[14.5px] text-fg-3 md:mb-10">
            {running} sessions running · <Delta v={ACCOUNT.today}>{signedUsd(ACCOUNT.today)}</Delta>{' '}
            so far · next rebalance Mon Nov 23
          </p>
          <Composer
            size="hero"
            reads={[
              'Account',
              `${running} sessions`,
              `${STRATEGIES.length} strategies`,
              `${BACKTESTS.length} backtests`,
            ]}
            suggestions={[
              'Why is the account down today?',
              "Lower Recession Radar's gold to 30%",
              'What has drifted from target?',
              'Draft a trend strategy on QQQ',
            ]}
          />
        </div>
        <Brief />
        <SinceLastLooked />
        <UpNext />
        <AccountLine />
        <Block
          title="Strategies and sessions"
          meta={`${running} running · ${RESTING.length} not running · open a row for its outline`}
        >
          <LedgerHead />
          <StrategyLedger rows={RUNNING} />
          <div className="mt-8 border-b border-line pb-2 text-[11.5px] font-medium text-fg-3">
            Not running
          </div>
          <StrategyLedger rows={RESTING} />
        </Block>
        <Foot
          items={[
            'Prices Nov 20, 2026, 12:04 ET',
            'paper and live trading on Alpaca',
            'history before Nov 12 is sample data',
          ]}
        />
      </div>
    </div>
  );
}
