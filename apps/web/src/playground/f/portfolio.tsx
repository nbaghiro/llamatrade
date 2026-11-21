import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ACCOUNT, pct, SAMPLE_FUND_RETURNS, signedUsd, strategyById, usd } from '../data';

import { Legend, PerfChart } from './chart';
import { Head, Page } from './frame';
import { useListNav } from './keys';
import {
  accountWindow,
  ASSET_CLASSES,
  dayLabel,
  drawdown,
  FUND_NAME,
  FUND_TODAY,
  fundSpark,
  HOLDINGS,
  pts,
  pts2,
  RANGES,
  to,
  tone,
  type Range,
} from './model';
import { rowClass } from './styles';
import { Block, Delta, Seg, Spark, Stats, TableHead } from './ui';

const shade = (i: number) => `rgb(var(--fg) / ${Math.max(0.14, 0.9 - i * 0.13).toFixed(2)})`;

function AccountBlock() {
  const [range, setRange] = useState<Range>('1Y');
  const w = accountWindow(range);
  const n = w.main.length;
  const ea = w.main[n - 1];
  const eb = w.bench[n - 1];
  const dd = Math.min(...drawdown(w.main));
  const ddb = Math.min(...drawdown(w.bench));
  return (
    <Block
      title="Account vs SPY"
      right={
        <>
          <Legend markers={w.markers.length > 0} />
          <Seg
            label="Range"
            value={range}
            onChange={setRange}
            options={RANGES.map((r) => ({ key: r, label: r }))}
          />
        </>
      }
      className="col-span-12 lg:col-span-8"
    >
      <Stats
        className="border-b border-line"
        items={[
          {
            label: `Return ${range}`,
            value: <span className={tone(ea)}>{pts(ea)}</span>,
            sub: `SPY ${pts(eb)}`,
          },
          {
            label: 'vs SPY',
            value: `${ea - eb >= 0 ? '+' : '−'}${Math.abs(ea - eb).toFixed(1)} pts`,
            sub: ea >= eb ? 'ahead' : 'behind',
          },
          { label: 'Max drawdown', value: pts(dd), sub: `SPY ${pts(ddb)}` },
          {
            label: 'Live',
            value: usd(ACCOUNT.live),
            sub: `${((ACCOUNT.live / ACCOUNT.total) * 100).toFixed(0)}% of account`,
          },
        ]}
      />
      <div className="px-3 pb-2 pt-3">
        <PerfChart w={w} height={232} ddHeight={48} />
      </div>
      {w.markers.length > 0 && (
        <ol className="m-0 flex list-none flex-wrap gap-x-5 border-t border-line px-3 py-1.5">
          {w.markers.map((m) => (
            <li key={m.n} className="flex h-6 items-center gap-2 text-[11.5px] text-fg-2">
              <i className="grid h-3.5 w-3.5 place-items-center rounded-[2px] border border-line-strong font-mono text-[9px] not-italic text-fg">
                {m.n}
              </i>
              <span className="font-mono text-[10.5px] text-fg-3">{dayLabel(w.dates[m.i])}</span>
              {m.label}
            </li>
          ))}
        </ol>
      )}
    </Block>
  );
}

function ClassesBlock() {
  const [hot, setHot] = useState<string | null>(null);
  return (
    <Block
      title="Asset classes"
      meta="by kind of fund, with cash"
      className="col-span-12 self-start lg:col-span-4"
    >
      <div className="px-3 pt-3">
        <div className="flex h-6 w-full overflow-hidden rounded-[3px]">
          {ASSET_CLASSES.map((c, i) => (
            <span
              key={c.name}
              onMouseEnter={() => setHot(c.name)}
              onMouseLeave={() => setHot(null)}
              className={`block h-full border-r border-canvas transition-opacity last:border-r-0 ${hot && hot !== c.name ? 'opacity-30' : ''}`}
              style={{
                width: `${(c.value / ACCOUNT.total) * 100}%`,
                background:
                  c.name === 'Cash'
                    ? 'repeating-linear-gradient(135deg, var(--hatch) 0 2px, transparent 2px 5px)'
                    : shade(i),
              }}
            />
          ))}
        </div>
      </div>
      <div className="mt-3 border-t border-line">
        {ASSET_CLASSES.map((c, i) => (
          <div
            key={c.name}
            onMouseEnter={() => setHot(c.name)}
            onMouseLeave={() => setHot(null)}
            className={`${rowClass(hot === c.name)} grid-cols-[10px_minmax(0,1fr)_44px_92px_64px]`}
          >
            <i
              className={`h-2 w-2 rounded-[1px] ${c.name === 'Cash' ? 'border border-fg-3' : ''}`}
              style={c.name === 'Cash' ? undefined : { background: shade(i) }}
            />
            <span className="min-w-0">
              <span className="block truncate text-[12.5px] text-fg">{c.name}</span>
            </span>
            <span className="text-right font-mono text-[11.5px] tabular-nums text-fg-2">
              {((c.value / ACCOUNT.total) * 100).toFixed(1)}%
            </span>
            <span className="text-right font-mono text-[12px] tabular-nums text-fg">
              {usd(c.value)}
            </span>
            <Delta v={c.today} className="text-right text-[11.5px]">
              {c.today === 0 ? '·' : `${c.today > 0 ? '+' : '−'}$${Math.abs(c.today).toFixed(0)}`}
            </Delta>
          </div>
        ))}
      </div>
      <p className="m-0 border-t border-line px-3 py-2 font-mono text-[10.5px] text-fg-3">
        Cash includes the stopped Tech Momentum session.
      </p>
    </Block>
  );
}

type Period = '1M' | '3M' | 'YTD' | '1Y';
const COLS =
  'grid-cols-[48px_minmax(0,1fr)_96px] md:grid-cols-[48px_minmax(0,1fr)_104px_64px_64px_56px_104px_minmax(0,200px)]';

function HoldingsBlock() {
  const nav = useNavigate();
  const [period, setPeriod] = useState<Period>('1Y');
  const open = useCallback((i: number) => nav(to(`/strategies/${HOLDINGS[i].sessions[0]}`)), [nav]);
  const [sel, setSel] = useListNav(HOLDINGS.length, { open });
  return (
    <Block
      title="Holdings"
      meta="each fund across every running session"
      right={
        <Seg
          label="Period"
          value={period}
          onChange={setPeriod}
          options={(['1M', '3M', 'YTD', '1Y'] as const).map((p) => ({ key: p, label: p }))}
        />
      }
      className="col-span-12"
    >
      <TableHead cols={COLS}>
        <span>Fund</span>
        <span />
        <span className="hidden md:block">Past year</span>
        <span className="hidden text-right md:block">{period}</span>
        <span className="hidden text-right md:block">Today</span>
        <span className="hidden text-right md:block">Weight</span>
        <span className="text-right">Value</span>
        <span className="hidden md:block">Held by</span>
      </TableHead>
      {HOLDINGS.map((h, i) => {
        const r = SAMPLE_FUND_RETURNS[h.symbol]?.[period] ?? 0;
        const t = FUND_TODAY[h.symbol] ?? 0;
        return (
          <div
            key={h.symbol}
            role="row"
            aria-selected={i === sel}
            onMouseEnter={() => setSel(i)}
            onClick={() => open(i)}
            className={`${rowClass(i === sel)} ${COLS}`}
          >
            <span className="font-mono text-[12px] font-medium text-fg">{h.symbol}</span>
            <span className="truncate text-[12.5px] text-fg-3">{FUND_NAME[h.symbol]}</span>
            <span className="hidden md:block">
              <Spark values={fundSpark(h.symbol)} width={96} height={18} />
            </span>
            <span
              className={`hidden text-right font-mono text-[12px] tabular-nums md:block ${tone(r)}`}
            >
              {pts2(r, 1)}
            </span>
            <Delta v={t} className="hidden text-right text-[12px] md:block">
              {pts2(t)}
            </Delta>
            <span className="hidden text-right font-mono text-[12px] tabular-nums text-fg-2 md:block">
              {((h.value / ACCOUNT.total) * 100).toFixed(1)}%
            </span>
            <span className="text-right font-mono text-[12.5px] tabular-nums text-fg">
              {usd(h.value)}
            </span>
            <span className="hidden truncate text-[12px] text-fg-3 md:block">
              {h.sessions.map((id) => strategyById(id)?.name).join(', ')}
              <span className="font-mono text-[10.5px]">
                {' · '}
                {h.live > 0 && h.paper > 0 ? 'live, paper' : h.live > 0 ? 'live' : 'paper'}
              </span>
            </span>
          </div>
        );
      })}
    </Block>
  );
}

export function Portfolio() {
  return (
    <Page
      art="own"
      head={
        <Head
          crumb="Portfolio · live and paper"
          title={<span className="font-mono tracking-[-0.04em]">{usd(ACCOUNT.total)}</span>}
          figure={
            <Delta v={ACCOUNT.today} className="text-[13px]">
              {signedUsd(ACCOUNT.today)} {pct(ACCOUNT.today / (ACCOUNT.total - ACCOUNT.today), 2)}
            </Delta>
          }
          meta={`live ${usd(ACCOUNT.live)} · paper ${usd(ACCOUNT.paper)} · ${HOLDINGS.length} funds held · fund returns are sample`}
        />
      }
    >
      <AccountBlock />
      <ClassesBlock />
      <HoldingsBlock />
    </Page>
  );
}
