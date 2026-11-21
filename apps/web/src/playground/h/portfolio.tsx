import { useState } from 'react';

import { ACCOUNT, SAMPLE_FUND_RETURNS, strategyById, usd } from '../data';

import { Stat } from './briefs';
import { Dateline, Lead, Page } from './frame';
import {
  accountWindow,
  ASSET_CLASSES,
  CASH,
  FUND_NAME,
  FUND_TODAY,
  fundSpark,
  HOLDINGS,
  pts,
  pts2,
  RANGE_WORDS,
  RANGES,
  tone,
} from './model';
import { Delta, Kicker, Segmented, Spark, Spread, TextLink } from './ui';

const shade = (i: number) => `rgb(var(--fg) / ${Math.max(0.12, 0.92 - i * 0.13).toFixed(2)})`;
type Period = '1M' | '3M' | 'YTD' | '1Y';

function AssetClasses() {
  const [hot, setHot] = useState<string | null>(null);
  const total = ACCOUNT.total;
  return (
    <section>
      <Kicker right="share of the account, with cash">Asset classes</Kicker>
      <div className="mt-5 flex h-14 w-full overflow-hidden">
        {ASSET_CLASSES.map((c, i) => (
          <span
            key={c.name}
            onMouseEnter={() => setHot(c.name)}
            onMouseLeave={() => setHot(null)}
            className={`relative block h-full border-r-2 border-canvas transition-opacity last:border-r-0 ${hot && hot !== c.name ? 'opacity-30' : ''}`}
            style={{
              width: `${(c.value / total) * 100}%`,
              background:
                c.name === 'Cash'
                  ? 'repeating-linear-gradient(135deg, var(--hatch) 0 2px, transparent 2px 6px)'
                  : shade(i),
            }}
          />
        ))}
      </div>
      <div className="mt-1 flex w-full font-mono text-[11px] tabular-nums text-fg-3">
        {ASSET_CLASSES.map((c) => (
          <span
            key={c.name}
            className="block truncate pr-1"
            style={{ width: `${(c.value / total) * 100}%` }}
          >
            {(c.value / total) * 100 >= 6 ? `${((c.value / total) * 100).toFixed(0)}%` : ''}
          </span>
        ))}
      </div>
      <div className="mt-5 border-t border-line">
        {ASSET_CLASSES.map((c, i) => (
          <div
            key={c.name}
            onMouseEnter={() => setHot(c.name)}
            onMouseLeave={() => setHot(null)}
            className={`grid grid-cols-[14px_minmax(0,1fr)_64px_110px] items-center gap-3 border-b border-line py-2.5 text-[13px] md:grid-cols-[14px_minmax(0,1fr)_150px_64px_120px_90px] ${hot === c.name ? 'bg-panel/70' : ''}`}
          >
            <i
              className={`h-2.5 w-2.5 rounded-[2px] ${c.name === 'Cash' ? 'border border-fg-3' : ''}`}
              style={c.name === 'Cash' ? undefined : { background: shade(i) }}
            />
            <span className="truncate text-fg">{c.name}</span>
            <span className="hidden truncate font-mono text-[11.5px] text-fg-3 md:block">
              {c.symbols.join(' ') || 'Stopped session and unused cash'}
            </span>
            <span className="text-right font-mono tabular-nums text-fg-2">
              {((c.value / total) * 100).toFixed(1)}%
            </span>
            <span className="text-right font-mono tabular-nums text-fg">{usd(c.value)}</span>
            <Delta v={c.today} className="hidden text-right text-[12.5px] md:block">
              {c.today === 0 ? '' : `${c.today > 0 ? '+' : '−'}$${Math.abs(c.today).toFixed(2)}`}
            </Delta>
          </div>
        ))}
      </div>
    </section>
  );
}

const HCOLS =
  'grid-cols-[52px_minmax(0,1fr)_100px] md:grid-cols-[52px_minmax(0,1fr)_110px_68px_68px_110px]';

function Holdings() {
  const [period, setPeriod] = useState<Period>('1Y');
  return (
    <section>
      <Kicker
        right={
          <Segmented
            label="Period"
            value={period}
            onChange={setPeriod}
            options={(['1M', '3M', 'YTD', '1Y'] as const).map((p) => ({ key: p, label: p }))}
          />
        }
      >
        Holdings
      </Kicker>
      <div
        className={`mt-3 grid ${HCOLS} gap-3 border-b border-line pb-2 text-[11.5px] font-medium text-fg-3`}
      >
        <span>Fund</span>
        <span>Held by</span>
        <span className="hidden md:block">Past year</span>
        <span className="hidden text-right md:block">{period}</span>
        <span className="hidden text-right md:block">Today</span>
        <span className="text-right">Value</span>
      </div>
      {HOLDINGS.map((h) => {
        const r = SAMPLE_FUND_RETURNS[h.symbol]?.[period] ?? 0;
        const t = FUND_TODAY[h.symbol] ?? 0;
        return (
          <div
            key={h.symbol}
            className={`grid ${HCOLS} items-center gap-3 border-b border-line py-2.5 text-[13px]`}
          >
            <span className="font-mono font-medium text-fg">{h.symbol}</span>
            <span className="min-w-0">
              <span className="block truncate text-fg-2">{FUND_NAME[h.symbol]}</span>
              <span className="block truncate text-[11.5px] text-fg-3">
                {h.sessions.map((id) => strategyById(id)?.name).join(', ')}
              </span>
            </span>
            <span className="hidden md:block">
              <Spark values={fundSpark(h.symbol)} width={100} height={24} />
            </span>
            <span className={`hidden text-right font-mono tabular-nums md:block ${tone(r)}`}>
              {pts2(r, 1)}
            </span>
            <Delta v={t} className="hidden text-right text-[12.5px] md:block">
              {pts2(t)}
            </Delta>
            <span className="text-right font-mono tabular-nums text-fg">{usd(h.value)}</span>
          </div>
        );
      })}
    </section>
  );
}

export function Portfolio() {
  const top = ASSET_CLASSES[0];
  const liveShare = ACCOUNT.live / ACCOUNT.total;
  return (
    <Page ask={{ placeholder: 'Ask about the account, holdings or risk' }}>
      <Lead
        kicker={`Portfolio · ${usd(ACCOUNT.total)} · ${HOLDINGS.length} funds`}
        headline={`${top.name} are the largest class, ${((top.value / ACCOUNT.total) * 100).toFixed(0)}% of the account`}
        deck={`${(liveShare * 100).toFixed(0)}% is live, the rest is paper.`}
      />
      <Spread
        main={
          <>
            <AssetClasses />
            <div className="mt-14">
              <Holdings />
            </div>
          </>
        }
        aside={
          <>
            <section className="mb-9">
              <Kicker>Account</Kicker>
              <Stat label="Total">{usd(ACCOUNT.total)}</Stat>
              <Stat label="Live" sub={`${(liveShare * 100).toFixed(0)}%`}>
                {usd(ACCOUNT.live)}
              </Stat>
              <Stat label="Paper" sub={`${((1 - liveShare) * 100).toFixed(0)}%`}>
                {usd(ACCOUNT.paper)}
              </Stat>
              <Stat label="Cash" sub={`${((CASH / ACCOUNT.total) * 100).toFixed(0)}%`}>
                {usd(CASH)}
              </Stat>
            </section>
            <section className="mb-9">
              <Kicker right="account · SPY">Against SPY</Kicker>
              {RANGES.map((r) => {
                const w = accountWindow(r);
                const n = w.main.length;
                return (
                  <div
                    key={r}
                    className="grid grid-cols-[minmax(0,1fr)_72px_112px] items-center gap-3 border-b border-line py-2.5 last:border-b-0"
                  >
                    <span className="text-[12.5px] text-fg-2">{RANGE_WORDS[r]}</span>
                    <Spark values={w.main} bench={w.bench} width={72} height={20} toneBy={false} />
                    <span className="text-right font-mono text-[13px] tabular-nums">
                      <span className={tone(w.main[n - 1])}>{pts(w.main[n - 1])}</span>
                      <span className="ml-2 text-[11px] text-fg-3">{pts(w.bench[n - 1])}</span>
                    </span>
                  </div>
                );
              })}
              <div className="mt-3">
                <TextLink to="/h">Chart on Today</TextLink>
              </div>
            </section>
          </>
        }
      />
      <Dateline
        items={['Prices Nov 20, 2026, 12:04 ET', 'fund returns and history are sample data']}
      />
    </Page>
  );
}
