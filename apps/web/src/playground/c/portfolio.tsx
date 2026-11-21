import { useState } from 'react';

import { ACCOUNT, SAMPLE_FUND_RETURNS, strategyById, usd } from '../data';

import { Page, PageHead } from './frame';
import { ASSET_CLASSES, FUND_NAME, FUND_TODAY, fundSpark, HOLDINGS, pts2, tone } from './model';
import { AccountPanel } from './today';
import { Delta, Foot, SectionHead, Segmented, Spark } from './ui';

const shade = (i: number) => `rgb(var(--fg) / ${Math.max(0.12, 0.92 - i * 0.12).toFixed(2)})`;
type Period = '1M' | '3M' | 'YTD' | '1Y';

function AssetClasses() {
  const [hot, setHot] = useState<string | null>(null);
  const total = ACCOUNT.total;
  return (
    <div>
      <SectionHead
        title="Asset classes"
        meta="What the account holds, by kind of fund, with cash"
      />
      <div className="flex h-9 w-full overflow-hidden rounded-[6px] border border-line">
        {ASSET_CLASSES.map((c, i) => (
          <span
            key={c.name}
            onMouseEnter={() => setHot(c.name)}
            onMouseLeave={() => setHot(null)}
            className={`relative block h-full border-r border-canvas transition-opacity last:border-r-0 ${''} ${hot && hot !== c.name ? 'opacity-30' : ''}`}
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
      <div className="mt-4 border-t border-line">
        {ASSET_CLASSES.map((c, i) => (
          <div
            key={c.name}
            onMouseEnter={() => setHot(c.name)}
            onMouseLeave={() => setHot(null)}
            className={`grid grid-cols-[14px_minmax(0,1fr)_64px_110px] items-center gap-3 border-b border-line py-2.5 text-[13px] md:grid-cols-[14px_minmax(0,1fr)_160px_64px_120px_100px] ${hot === c.name ? 'bg-panel/70' : ''}`}
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
    </div>
  );
}

function Holdings() {
  const [period, setPeriod] = useState<Period>('1Y');
  return (
    <div>
      <SectionHead
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
      />
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
    </div>
  );
}

export function Portfolio() {
  return (
    <Page ask={{ placeholder: 'Ask about the account, holdings or risk' }} art="own">
      <PageHead
        eyebrow="Nov 20, 2026 · 12:04 ET"
        title="Portfolio"
        meta={`${usd(ACCOUNT.total)} across live and paper · ${HOLDINGS.length} funds held`}
      />
      <AccountPanel title="Whole account" />
      <div className="mt-14 grid gap-12">
        <AssetClasses />
        <Holdings />
      </div>
      <Foot items={['Prices Nov 20, 2026, 12:04 ET', 'fund returns and history are sample data']} />
    </Page>
  );
}
