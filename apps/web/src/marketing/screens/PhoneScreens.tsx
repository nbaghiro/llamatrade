import { useId, type ReactNode } from 'react';

import { Sparkline } from '../../components/charts';
import { LogoMark } from '../../components/common/Logo';
import { areaPath, linePath, xAt, yAt, yDomain, type Plot } from '../../lib/chart/scale';
import { formatMoney, formatPct, pnlTone } from '../../lib/format';
import { PhoneArt } from '../components/PhoneArt';
import {
  accountMonth,
  dayChange,
  EQUITY,
  momentumLines,
  shortDate,
  sleeveRows,
  techMomentum,
} from '../data/illustrative';
import type { SectionArtId } from '../lib/sectionArt';

/** Width of the phone screen inside the bezel, in design px. */
const SCREEN_W = 390;
const CONTENT_W = SCREEN_W - 40;

const TABS = ['Home', 'Sessions', 'Markets', 'Activity', 'Account'] as const;
type Tab = (typeof TABS)[number];

const TAB_ICON: Record<Tab, string> = {
  Home: 'M4 11 12 4l8 7v9h-5v-6H9v6H4z',
  Sessions: 'M3 12h4l2.5-6 5 12 2.5-6h4',
  Markets: 'M4 4v16h16M7 15l4-4 3 3 5-6',
  Activity: 'M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15zM10 20.5h4',
  Account: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.5 20.5a7.5 7.5 0 0 1 15 0',
};

function Icon({ d, size = 24 }: { d: string; size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      <path d={d} fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinejoin="round" />
    </svg>
  );
}

function StatusBar({ time = true }: { time?: boolean }) {
  return (
    <div className="sb">
      <span>{time ? '10:42' : ''}</span>
      <span className="sb-r">
        <svg viewBox="0 0 18 12" width={18} height={12} aria-hidden="true">
          {[0, 1, 2, 3].map((i) => (
            <rect key={i} x={i * 4.6} y={8 - i * 2.6} width={3} height={4 + i * 2.6} rx={0.8} />
          ))}
        </svg>
        <i />
      </span>
    </div>
  );
}

function TabBar({ on }: { on: Tab }) {
  return (
    <div className="mtabs">
      {TABS.map((t) => (
        <span key={t} className={t === on ? 'on' : undefined}>
          <Icon d={TAB_ICON[t]} />
          {t}
        </span>
      ))}
    </div>
  );
}

function PhoneShell({
  art,
  footer,
  children,
}: {
  art?: { shape: SectionArtId; height: number };
  footer: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      {art && (
        <PhoneArt
          shape={art.shape}
          width={SCREEN_W}
          height={art.height}
          top={art.height * 0.16}
          band={art.height * 0.5}
        />
      )}
      <StatusBar />
      <div className="body">{children}</div>
      {footer}
      <span className="home-ind" />
    </>
  );
}

function Delta({ value, base, money = true }: { value: number; base: number; money?: boolean }) {
  const tone = pnlTone(value);
  return (
    <span className={`dchips ${tone}`}>
      {money && <span>{formatMoney(value, { signed: true })}</span>}
      <span>{formatPct(dayChange(base, value), { signed: true })}</span>
    </span>
  );
}

interface CurveMark {
  at: number;
  label: string;
}

/** A filled equity curve with an optional dashed benchmark, marked days and a future column. */
function Curve({
  values,
  bench,
  height,
  marks = [],
  future = 0,
  ticks = [],
}: {
  values: readonly number[];
  bench?: readonly number[];
  height: number;
  marks?: readonly CurveMark[];
  /** Width of the dashed column after the last value, in px. */
  future?: number;
  /** Labels under the curve at a value index, or at the end of the future column. */
  ticks?: readonly { at: number | 'next'; label: string }[];
}) {
  const fill = `pc-${useId().replace(/:/g, '')}`;
  const plot: Plot = {
    width: SCREEN_W,
    height,
    pad: { t: 22, r: 14 + future, b: 4, l: 0 },
    domain: yDomain(bench ? [values, bench] : [values]),
    count: values.length,
  };
  const last = values.length - 1;
  const endX = xAt(plot, last);
  const endY = yAt(plot, values[last]);
  return (
    <svg
      className="curve"
      width={SCREEN_W}
      height={height + (ticks.length ? 22 : 0)}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={fill} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="rgb(var(--accent))" stopOpacity="0.34" />
          <stop offset="1" stopColor="rgb(var(--accent))" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath(plot, values, plot.domain.lo)} fill={`url(#${fill})`} />
      {bench && <path d={linePath(plot, bench)} className="bench" />}
      <path d={linePath(plot, values)} className="main" />
      {marks.map((m) => {
        const x = xAt(plot, m.at);
        return (
          <g key={m.label}>
            <line x1={x} x2={x} y1={14} y2={height} className="guide" />
            <circle cx={x} cy={yAt(plot, values[m.at])} r={5} className="mark" />
            <text x={x + 6} y={12} className="mlabel">
              {m.label}
            </text>
          </g>
        );
      })}
      {future > 0 && (
        <g>
          <line x1={endX} x2={endX + future} y1={endY} y2={endY} className="plan" />
          <line x1={endX + future} x2={endX + future} y1={14} y2={height} className="guide" />
          <circle cx={endX + future} cy={endY} r={5} className="mark open" />
          <text x={endX + future - 6} y={12} className="mlabel" textAnchor="end">
            Next
          </text>
        </g>
      )}
      {ticks.map((t, i) => (
        <text
          key={t.label}
          x={t.at === 'next' ? endX + future : Math.max(20, xAt(plot, t.at))}
          y={height + 18}
          className="tick"
          textAnchor={i === ticks.length - 1 ? 'end' : i === 0 ? 'start' : 'middle'}
        >
          {t.label}
        </text>
      ))}
      <circle cx={endX} cy={endY} r={11} className="halo" />
      <circle cx={endX} cy={endY} r={5.5} className="dot" />
    </svg>
  );
}

function money(v: number): string {
  return formatMoney(v);
}

export function HomePhone() {
  const am = accountMonth();
  return (
    <PhoneShell art={{ shape: 'top', height: 300 }} footer={<TabBar on="Home" />}>
      <div className="topbar">
        <LogoMark size={30} bold />
        <Icon d="M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4" />
      </div>
      <div>
        <span className="lbl">Total equity · Nov 13</span>
        <div className="big">{money(EQUITY.total)}</div>
        <div className="sub">
          <Delta value={EQUITY.today} base={EQUITY.total} />
          <span className="t3">today</span>
        </div>
      </div>
      <div className="bleed">
        <Curve values={am.account} bench={am.benchmark} height={168} />
        <div className="axis">
          <span>{shortDate(am.days[0])}</span>
          <span className="bench-key">SPY</span>
          <span>{shortDate(am.days[am.days.length - 1])}</span>
        </div>
      </div>
      <div className="hint">
        <i />
        <span>
          <b>Recession Radar is frozen.</b> Alpaca reports 120 TLT shares, the ledger 167.
        </span>
      </div>
      <div className="mhead">
        <b>Sessions</b>
        <span className="acc">See all</span>
      </div>
      <div className="list">
        {sleeveRows().map((s) => {
          const tone = pnlTone(s.today) === 'loss' ? 'loss' : 'gain';
          return (
            <div key={s.name} className="srow">
              <span className="nm">
                <b className={s.state === 'frozen' ? 'risk' : undefined}>{s.name}</b>
                <span className={s.state === 'frozen' ? 'risk' : 't3'}>{s.note}</span>
              </span>
              <Sparkline values={s.month} width={64} height={30} tone={tone} className="spark" />
              <span className="fig">
                {money(s.equity)}
                <span className={tone}>
                  {formatPct(dayChange(s.equity, s.today), { signed: true })}
                </span>
              </span>
            </div>
          );
        })}
      </div>
    </PhoneShell>
  );
}

const HOLDINGS: readonly [string, string, number, number, number][] = [
  ['QQQ', '20 shares', 12_379.0, 49.7, 0.0289],
  ['SMH', '42 shares', 12_150.6, 48.8, 0.0446],
];

export function SessionPhone() {
  const tm = techMomentum();
  const equity = tm.equity[tm.equity.length - 1];
  const total = equity - tm.allocated;
  return (
    <PhoneShell
      art={{ shape: 'own', height: 260 }}
      footer={
        <div className="actbar">
          <span>
            <Icon d="M9 6v12M15 6v12" size={20} />
            Pause
          </span>
          <span>
            <Icon d="M5 5h14v14H5zM5 10h14" size={20} />
            Orders
          </span>
          <span className="pri">
            <Icon d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" size={20} />
            Ask
          </span>
        </div>
      }
    >
      <div className="navbar">
        <span className="acc">‹ Home</span>
        <span className="t3">•••</span>
      </div>
      <div>
        <h4>Tech Momentum Rotation</h4>
        <div className="badges">
          <span className="badge live">Live</span>
          <span className="t2">
            <i className="run" />
            Running since Oct 1
          </span>
        </div>
      </div>
      <div>
        <div className="big">{money(equity)}</div>
        <div className="sub">
          <Delta value={tm.today} base={equity} />
          <span className={`${pnlTone(total)} mono`}>
            {formatMoney(total, { signed: true })} since Oct 1
          </span>
        </div>
      </div>
      <div className="bleed">
        <Curve
          values={tm.equity}
          height={176}
          future={54}
          marks={[{ at: tm.rebalanceAt, label: 'Rebalanced' }]}
          ticks={[
            { at: 0, label: 'Oct 1' },
            { at: tm.rebalanceAt, label: shortDate(tm.days[tm.rebalanceAt]) },
            { at: 'next', label: 'Dec 1' },
          ]}
        />
      </div>
      <div className="mcard">
        <div className="mcard-h">
          <b>Rebalances Dec 1</b>
          <span className="t3 mono">to 50 / 50</span>
        </div>
        {HOLDINGS.map(([sym, qty, value, weight, today]) => (
          <div key={sym} className="hold">
            <span className="sym">
              <b>{sym}</b>
              <span className="t3">{qty}</span>
            </span>
            <span className="track">
              <span style={{ width: `${weight}%` }} />
              <i />
            </span>
            <span className="fig">
              {money(value)}
              <span className="gain">{formatPct(today, { signed: true })}</span>
            </span>
          </div>
        ))}
      </div>
    </PhoneShell>
  );
}

export function AlertsPhone() {
  return (
    <>
      <PhoneArt
        shape="build"
        width={SCREEN_W}
        height={822}
        top={822 * 0.34}
        band={822 * 0.3}
        full
      />
      <StatusBar time={false} />
      <div className="lock">
        <div className="lock-date">Friday, November 13</div>
        <div className="lock-time">10:42</div>
        <div className="widget">
          <span className="lbl">LlamaTrade · equity</span>
          <b>{money(EQUITY.total)}</b>
          <span>{formatMoney(EQUITY.today, { signed: true })} today</span>
        </div>
        <div className="notes">
          <Notice
            time="10:31"
            title="An order was not sent"
            body="Tech Momentum Rotation's buy of 16 SMH would pass the session's $10,000 position limit."
          />
          <Notice
            time="10:15"
            title="Recession Radar is frozen"
            body="Alpaca reports 120 TLT shares and the ledger expects 167. New orders wait until you review it."
            urgent
          />
        </div>
        <div className="lock-foot">
          <span>
            <Icon d="M13 3 6 13h5l-1 8 7-10h-5z" size={22} />
          </span>
          <span>
            <Icon d="M3 12s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6zM12 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z" />
          </span>
        </div>
      </div>
      <span className="home-ind" />
    </>
  );
}

function Notice({
  time,
  title,
  body,
  urgent = false,
}: {
  time: string;
  title: string;
  body: string;
  urgent?: boolean;
}) {
  return (
    <div className={urgent ? 'note urgent' : 'note'}>
      <span className="app-ic">
        <LogoMark size={26} bold />
      </span>
      <span className="note-b">
        {urgent && <span className="ts">Time sensitive</span>}
        <span className="note-h">
          <b>{title}</b>
          <span>{time}</span>
        </span>
        <span>{body}</span>
      </span>
    </div>
  );
}

export function CopilotPhone() {
  const lines = momentumLines();
  const all = lines.flatMap((l) => l.values);
  const plot: Plot = {
    width: CONTENT_W - 28,
    height: 128,
    pad: { t: 8, r: 64, b: 8, l: 0 },
    domain: yDomain([all]),
    count: lines[0].values.length,
  };
  const labelY: number[] = [];
  lines.forEach((l, i) => {
    const y = yAt(plot, l.values[l.values.length - 1]) + 4;
    labelY.push(i ? Math.max(y, labelY[i - 1] + 15) : y);
  });
  return (
    <>
      <StatusBar />
      <div className="sheet">
        <PhoneArt shape="copilot" width={SCREEN_W} height={220} top={30} band={130} />
        <span className="grab" />
        <div className="sheet-h">
          <span className="ctx">
            <Icon d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" size={16} />
            Copilot
          </span>
          <span className="x">×</span>
        </div>
        <div className="body">
          <div className="me">
            Build me a momentum rotation across tech ETFs, rebalanced monthly.
          </div>
          <p className="ans">
            Rank QQQ, XLK and SMH by 90-day return each month and hold the top two at equal weight,
            with QQQ as the benchmark.
          </p>
          <div className="mcard draft">
            <div className="mcard-h">
              <b>Tech Momentum Rotation</b>
              <span className="chip ok">Valid</span>
            </div>
            <span className="lbl">90-day return to Nov 13</span>
            <svg width={plot.width} height={plot.height} className="mom" aria-hidden="true">
              {lines.map((l, i) => {
                const held = i < 2;
                return (
                  <g key={l.sym} className={held ? `held h${i}` : 'out'}>
                    <path d={linePath(plot, l.values)} />
                    <text x={plot.width - 58} y={labelY[i]}>
                      {l.sym} {formatPct(l.ret, { dp: 1, signed: true })}
                    </text>
                  </g>
                );
              })}
            </svg>
            <span className="lbl">Would hold today</span>
            <div className="wsplit">
              <span className="h0">SMH 50%</span>
              <span className="h1">QQQ 50%</span>
            </div>
            <span className="t3 small">XLK ranks third, so it isn&apos;t held this month.</span>
          </div>
          <div className="btns">
            <span className="mb">Backtest</span>
            <span className="mb s">Discard</span>
          </div>
        </div>
        <div className="ask">
          <span>Ask a follow-up</span>
          <i>
            <Icon
              d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0M12 17v4"
              size={20}
            />
          </i>
        </div>
      </div>
      <span className="home-ind" />
    </>
  );
}
