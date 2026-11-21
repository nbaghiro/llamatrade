import { useCallback, useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { BACKTESTS, strategyById } from '../data';

import { Legend, PerfChart } from './chart';
import { useCopilot } from './copilotContext';
import { Head, Page } from './frame';
import { useListNav } from './keys';
import { backtestWindow, drawdown, pts, to, tone, type Window } from './model';
import { OutlineView } from './outline';
import { itemsOf } from './outlineModel';
import { rowClass } from './styles';
import { Block, Button, Kbd, LinkButton, Mono, Spark, Stats, TableHead } from './ui';

const COLS =
  'grid-cols-[minmax(0,1fr)_72px] md:grid-cols-[minmax(0,1fr)_40px_64px_120px_80px_72px_72px_80px_56px]';

function QuickRun() {
  const { submit } = useCopilot();
  const [q, setQ] = useState('');
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit(q.trim().toLowerCase().startsWith('backtest') ? q : `backtest ${q}`);
        setQ('');
      }}
      className="flex h-7 w-[300px] max-w-full items-center gap-2 rounded-[6px] border border-line px-2.5 focus-within:border-line-strong"
    >
      <span className="font-mono text-[11.5px] text-fg-3">› backtest</span>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="risk parity 5y"
        aria-label="Quick backtest"
        className="min-w-0 flex-1 bg-transparent font-mono text-[11.5px] text-fg outline-none placeholder:text-fg-3"
      />
      <Kbd>↵</Kbd>
    </form>
  );
}

export function BacktestsList() {
  const nav = useNavigate();
  const open = useCallback((i: number) => nav(to(`/backtests/${BACKTESTS[i].id}`)), [nav]);
  const edit = useCallback((i: number) => nav(to(`/strategies/${BACKTESTS[i].strategyId}`)), [nav]);
  const [sel, setSel] = useListNav(BACKTESTS.length, { open, edit });
  return (
    <Page
      art="backtest"
      head={
        <Head
          crumb="Backtests"
          title="Backtests"
          meta={`${BACKTESTS.length} runs · two years each · $25,000 · benchmark SPY`}
          right={<QuickRun />}
        />
      }
    >
      <Block
        title="Runs"
        meta="newest first"
        right={<Legend main="Strategy" />}
        className="col-span-12"
      >
        <TableHead cols={COLS}>
          <span>Strategy</span>
          <span className="hidden md:block">Ver</span>
          <span className="hidden md:block">Ran</span>
          <span className="hidden md:block">Against SPY</span>
          <span className="text-right">Return</span>
          <span className="hidden text-right md:block">SPY</span>
          <span className="hidden text-right md:block">Excess</span>
          <span className="hidden text-right md:block">Worst</span>
          <span className="hidden text-right md:block">Sharpe</span>
        </TableHead>
        {BACKTESTS.map((b, i) => {
          const s = strategyById(b.strategyId);
          const w = backtestWindow(b);
          const ex = (b.ret - b.spy) * 100;
          return (
            <div
              key={b.id}
              role="row"
              aria-selected={i === sel}
              onMouseEnter={() => setSel(i)}
              onClick={() => open(i)}
              className={`${rowClass(i === sel)} ${COLS}`}
            >
              <span className="flex min-w-0 items-baseline gap-2">
                <span className="truncate font-medium text-fg">{s?.name}</span>
                <span className="hidden truncate font-mono text-[10.5px] text-fg-3 lg:inline">
                  {b.range}
                </span>
              </span>
              <span className="hidden font-mono text-[12px] text-fg-2 md:block">v{b.version}</span>
              <span className="hidden font-mono text-[11.5px] text-fg-3 md:block">{b.ran}</span>
              <span className="hidden md:block">
                <Spark values={w.main} bench={w.bench} width={112} height={18} toneBy={false} />
              </span>
              <span className={`text-right font-mono text-[12.5px] tabular-nums ${tone(b.ret)}`}>
                {pts(b.ret * 100)}
              </span>
              <span className="hidden text-right font-mono text-[12px] tabular-nums text-fg-3 md:block">
                {pts(b.spy * 100)}
              </span>
              <span
                className={`hidden text-right font-mono text-[12px] tabular-nums md:block ${tone(ex)}`}
              >
                {pts(ex)}
              </span>
              <span className="hidden text-right font-mono text-[12px] tabular-nums text-fg-2 md:block">
                {pts(b.worst * 100)}
              </span>
              <span className="hidden text-right font-mono text-[12px] tabular-nums text-fg-2 md:block">
                {b.sharpe.toFixed(2)}
              </span>
            </div>
          );
        })}
      </Block>
    </Page>
  );
}

const MON = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];

function monthly(w: Window) {
  const byMonth = new Map<string, { y: number; m: number; first: number; last: number }>();
  w.dates.forEach((d, i) => {
    const k = `${d.getUTCFullYear()}-${d.getUTCMonth()}`;
    const prev = i > 0 ? w.main[i - 1] : w.main[0];
    const cur = byMonth.get(k);
    if (cur) cur.last = w.main[i];
    else
      byMonth.set(k, { y: d.getUTCFullYear(), m: d.getUTCMonth(), first: prev, last: w.main[i] });
  });
  const ret = (a: number, b: number) => ((1 + b / 100) / (1 + a / 100) - 1) * 100;
  return [...byMonth.values()].map((v) => ({ ...v, r: ret(v.first, v.last) }));
}

function Monthly({ w }: { w: Window }) {
  const ms = monthly(w);
  const years = [...new Set(ms.map((v) => v.y))];
  return (
    <div className="overflow-x-auto px-3 py-2">
      <table className="w-full min-w-[600px] border-collapse font-mono text-[11px] tabular-nums">
        <thead>
          <tr className="text-fg-3">
            <th className="w-12 py-1 text-left font-normal" />
            {MON.map((m, i) => (
              <th key={i} className="py-1 font-normal">
                {m}
              </th>
            ))}
            <th className="py-1 text-right font-normal">Year</th>
          </tr>
        </thead>
        <tbody>
          {years.map((y) => {
            const row = ms.filter((x) => x.y === y);
            const yr = row.reduce((a, x) => a * (1 + x.r / 100), 1) * 100 - 100;
            return (
              <tr key={y}>
                <td className="py-0.5 text-fg-3">{y}</td>
                {MON.map((_, m) => {
                  const v = row.find((x) => x.m === m);
                  if (!v) return <td key={m} className="p-px" />;
                  const k = Math.min(1, Math.abs(v.r) / 6);
                  return (
                    <td key={m} className="p-px">
                      <span
                        className={`block rounded-[3px] py-1 text-center ${v.r >= 0 ? 'text-gain' : 'text-loss'}`}
                        style={{
                          background: `color-mix(in srgb, rgb(var(${v.r >= 0 ? '--gain' : '--loss'})) ${Math.round(6 + k * 22)}%, transparent)`,
                        }}
                      >
                        {v.r >= 0 ? '+' : '−'}
                        {Math.abs(v.r).toFixed(1)}
                      </span>
                    </td>
                  );
                })}
                <td className={`py-0.5 text-right ${tone(yr)}`}>{pts(yr)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function KeyValues({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <div>
      {rows.map(([k, v]) => (
        <div
          key={k}
          className="flex h-8 items-center justify-between gap-3 border-b border-line px-3 text-[12.5px] last:border-b-0"
        >
          <span className="text-fg-3">{k}</span>
          <span className="font-mono tabular-nums text-fg">{v}</span>
        </div>
      ))}
    </div>
  );
}

export function BacktestPage() {
  const { id = '' } = useParams();
  const { openBar } = useCopilot();
  const b = BACKTESTS.find((x) => x.id === id);
  const s = b ? strategyById(b.strategyId) : undefined;
  if (!b || !s)
    return (
      <Page head={<Head crumb="Backtests" title="Not found" />}>
        <p className="col-span-12 text-fg-2">This backtest could not be found.</p>
      </Page>
    );
  const w = backtestWindow(b);
  const spyDd = Math.min(...drawdown(w.bench));
  const ms = monthly(w);
  const best = ms.reduce((a, x) => (x.r > a.r ? x : a), ms[0]);
  const worstM = ms.reduce((a, x) => (x.r < a.r ? x : a), ms[0]);
  const label = (x: { y: number; m: number }) =>
    `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][x.m]} ${x.y}`;
  return (
    <Page
      art="backtest"
      head={
        <Head
          crumb={
            <>
              <Link to={to('/backtests')} className="hover:text-fg">
                Backtests
              </Link>{' '}
              / ran {b.ran}
            </>
          }
          title={`${s.name} v${b.version}`}
          figure={
            <span className={`font-mono text-[15px] tabular-nums ${tone(b.ret)}`}>
              {pts(b.ret * 100)}
            </span>
          }
          meta={`${b.range} · $25,000 · benchmark SPY`}
          right={
            <>
              <Button variant="primary">Start paper session</Button>
              <LinkButton to={to(`/strategies/${s.id}`)} k="e">
                Edit
              </LinkButton>
              <Button variant="quiet" k="/" onClick={() => openBar(s.id)}>
                Ask
              </Button>
            </>
          }
        />
      }
    >
      <Block title="Result" right={<Legend main={s.name} />} className="col-span-12 lg:col-span-8">
        <Stats
          className="border-b border-line"
          items={[
            {
              label: 'Return',
              value: <span className={tone(b.ret)}>{pts(b.ret * 100)}</span>,
              sub: `SPY ${pts(b.spy * 100)}`,
            },
            { label: 'Excess', value: pts((b.ret - b.spy) * 100), sub: 'against SPY' },
            { label: 'Sharpe', value: b.sharpe.toFixed(2), sub: 'SPY 0.77' },
            { label: 'Max drawdown', value: pts(b.worst * 100), sub: `SPY ${pts(spyDd)}` },
            {
              label: 'Ending',
              value: `$${Math.round(25000 * (1 + b.ret)).toLocaleString('en-US')}`,
              sub: 'from $25,000',
            },
            { label: 'Months up', value: `${ms.filter((x) => x.r > 0).length}/${ms.length}` },
          ]}
        />
        <div className="px-3 pb-2 pt-3">
          <PerfChart w={w} height={248} mainLabel={s.name} ddHeight={56} worst={b.worst * 100} />
        </div>
      </Block>
      <div className="col-span-12 grid content-start gap-3 lg:col-span-4">
        <Block title="Run" meta="sample for the playground">
          <KeyValues
            rows={[
              ['Range', b.range],
              ['Rebalances', s.cadence],
              [
                'Best month',
                <span key="b" className="text-gain">{`${pts(best.r)} · ${label(best)}`}</span>,
              ],
              [
                'Worst month',
                <span key="w" className="text-loss">{`${pts(worstM.r)} · ${label(worstM)}`}</span>,
              ],
              ['Ran', b.ran],
            ]}
          />
        </Block>
        <Block title={`Outline v${b.version}`}>
          <OutlineView strategy={s} items={itemsOf(s.name, s.cadence, s.rules)} compact />
        </Block>
      </div>
      <Block
        title="Monthly returns"
        meta="end of month to end of month"
        className="col-span-12 lg:col-span-8"
      >
        <Monthly w={w} />
      </Block>
      <div className="col-span-12 flex items-start lg:col-span-4">
        <Mono className="leading-relaxed text-fg-3">
          Past results do not predict future returns
        </Mono>
      </div>
    </Page>
  );
}
