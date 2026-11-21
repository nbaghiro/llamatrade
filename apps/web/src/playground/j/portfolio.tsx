import { useState } from 'react';

import { ACCOUNT, SAMPLE_FUND_RETURNS, strategyById, usd } from '../data';

import {
  ASSET_CLASSES,
  FUND_NAME,
  FUND_TODAY,
  fundSpark,
  HOLDINGS,
  pts2,
  slug,
  tone,
} from './model';
import {
  Delta,
  Figure,
  Figures,
  LeftHead,
  ListLabel,
  PanelFoot,
  PanelHead,
  PickRow,
  Segmented,
  Spark,
  StageCard,
} from './ui';

const shade = (i: number) => `rgb(var(--fg) / ${Math.max(0.14, 0.92 - i * 0.13).toFixed(2)})`;
const HATCH = 'repeating-linear-gradient(135deg, var(--hatch) 0 2px, transparent 2px 6px)';
const whole = (v: number) => usd(v).replace(/\.\d+$/, '');
type Period = '1M' | '3M' | 'YTD' | '1Y';

/** The funds the account holds, all of them or one asset class, on the stage. */
export function HoldingsPanel({ cls }: { cls: string }) {
  const [period, setPeriod] = useState<Period>('1Y');
  const klass = ASSET_CLASSES.find((c) => slug(c.name) === cls);
  const rows = klass ? HOLDINGS.filter((h) => klass.symbols.includes(h.symbol)) : HOLDINGS;
  const value = rows.reduce((a, h) => a + h.value, 0);
  const today = rows.reduce((a, h) => a + (h.value * (FUND_TODAY[h.symbol] ?? 0)) / 100, 0);
  return (
    <StageCard>
      <PanelHead
        eyebrow={klass ? 'Asset class' : 'Holdings'}
        title={klass ? klass.name : 'Every fund held'}
        meta={`${rows.length} ${rows.length === 1 ? 'fund' : 'funds'} across running sessions · prices Nov 20, 12:04 ET`}
        right={
          <Segmented
            label="Period"
            value={period}
            onChange={setPeriod}
            options={(['1M', '3M', 'YTD', '1Y'] as const).map((p) => ({ key: p, label: p }))}
          />
        }
      />
      <div className="mt-[18px]">
        <Figures>
          <Figure label="Value" sub={`of ${whole(ACCOUNT.total)}`}>
            {whole(value)}
          </Figure>
          <Figure label="Share of account" sub={klass ? 'by market value' : 'cash is the rest'}>
            {((value / ACCOUNT.total) * 100).toFixed(1)}%
          </Figure>
          <Figure label="Today" sub="at the last price">
            <span className={tone(today)}>
              {today >= 0 ? '+' : '−'}${Math.abs(today).toFixed(0)}
            </span>
          </Figure>
        </Figures>
      </div>
      <div className="mt-4">
        <div className="grid grid-cols-[52px_minmax(0,1fr)_96px_64px_64px_96px] gap-3 border-b border-line pb-2 text-[11px] font-medium text-fg-3">
          <span>Fund</span>
          <span />
          <span>Past year</span>
          <span className="text-right">{period}</span>
          <span className="text-right">Today</span>
          <span className="text-right">Value</span>
        </div>
        {rows.map((h) => {
          const r = SAMPLE_FUND_RETURNS[h.symbol]?.[period] ?? 0;
          const t = FUND_TODAY[h.symbol] ?? 0;
          return (
            <div
              key={h.symbol}
              className="grid grid-cols-[52px_minmax(0,1fr)_96px_64px_64px_96px] items-center gap-3 border-b border-line py-2.5 text-[13px]"
            >
              <span className="font-mono font-medium text-fg">{h.symbol}</span>
              <span className="min-w-0">
                <span className="block truncate text-fg-2">{FUND_NAME[h.symbol]}</span>
                <span className="block truncate text-[11.5px] text-fg-3">
                  {h.sessions.map((id) => strategyById(id)?.name).join(', ')}
                </span>
              </span>
              <Spark values={fundSpark(h.symbol)} width={92} height={22} />
              <span className={`text-right font-mono tabular-nums ${tone(r)}`}>{pts2(r, 1)}</span>
              <Delta v={t} className="text-right text-[12.5px]">
                {pts2(t)}
              </Delta>
              <span className="text-right font-mono tabular-nums text-fg">{whole(h.value)}</span>
            </div>
          );
        })}
      </div>
      <PanelFoot flush note="Fund returns and history are sample data for the playground." />
    </StageCard>
  );
}

export function PortfolioLeft({ sel }: { sel: string }) {
  const total = ACCOUNT.total;
  return (
    <>
      <LeftHead
        title="Portfolio"
        sub={`${HOLDINGS.length} funds across live and paper sessions.`}
      />
      <div className="mt-7">
        <span className="text-[11.5px] font-medium text-fg-3">Account value</span>
        <div className="mt-1 font-mono text-[34px] font-medium leading-none tracking-[-0.04em] tabular-nums text-fg">
          {usd(total)}
        </div>
        <div className="mt-2 text-[12.5px] text-fg-3">
          Live {whole(ACCOUNT.live)} · Paper {whole(ACCOUNT.paper)}
        </div>
      </div>
      <ListLabel>Views</ListLabel>
      <PickRow
        to="/j/portfolio"
        on={sel === 'account'}
        title="Account against SPY"
        sub="Return, drawdown and session markers"
      />
      <PickRow
        to="/j/portfolio?v=all"
        on={sel === 'all'}
        title="Every fund held"
        sub={`${HOLDINGS.length} funds · ${whole(HOLDINGS.reduce((a, h) => a + h.value, 0))}`}
      />
      <ListLabel right={<span>Share</span>}>By asset class</ListLabel>
      <div className="mb-2 mt-2 flex h-2.5 w-full overflow-hidden rounded-full">
        {ASSET_CLASSES.map((c, i) => (
          <span
            key={c.name}
            className="block h-full border-r border-canvas last:border-r-0"
            style={{
              width: `${(c.value / total) * 100}%`,
              background: c.name === 'Cash' ? HATCH : shade(i),
            }}
          />
        ))}
      </div>
      {ASSET_CLASSES.map((c, i) => {
        const row = (
          <span className="inline-flex min-w-0 items-center gap-2.5">
            <i
              className={`h-2.5 w-2.5 flex-none rounded-[2px] ${c.name === 'Cash' ? 'border border-fg-3' : ''}`}
              style={c.name === 'Cash' ? undefined : { background: shade(i) }}
            />
            <span className="truncate">{c.name}</span>
          </span>
        );
        const right = (
          <span className="font-mono text-[12.5px] tabular-nums text-fg-2">
            {((c.value / total) * 100).toFixed(1)}%
          </span>
        );
        if (c.name === 'Cash')
          return (
            <div
              key={c.name}
              className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 py-2.5 text-[13.5px] text-fg-2"
            >
              <span className="min-w-0">
                {row}
                <span className="mt-0.5 block pl-5 text-[12px] text-fg-3">
                  {whole(c.value)} · stopped session and unused cash
                </span>
              </span>
              {right}
            </div>
          );
        return (
          <PickRow
            key={c.name}
            to={`/j/portfolio?v=${slug(c.name)}`}
            on={sel === slug(c.name)}
            title={row}
            sub={
              <span className="pl-5">
                {c.symbols.join(' ')} · {whole(c.value)}
              </span>
            }
            right={right}
          />
        );
      })}
    </>
  );
}
