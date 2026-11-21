import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { strategyById } from '../data';

import { useAsk } from './askContext';
import { Page, PageHead } from './frame';
import { backtestWindow, pts, tone, type Window } from './model';
import { BACKTEST_COLS, backtestRows, RUNS } from './rows';
import { ACCOUNT_SCOPE, type Scope } from './scope';
import { ScopeSheet } from './sheet';
import { LedgerTree } from './tree';
import { Button, Foot, LinkButton, SectionHead } from './ui';

export function BacktestsList() {
  const { ask } = useAsk();
  const rows = useMemo(() => backtestRows(), []);
  const [scope, setScope] = useState<Scope>(() => rows[0].scope ?? ACCOUNT_SCOPE);
  return (
    <Page ask={false} art="backtest">
      <PageHead
        eyebrow="Nov 20, 2026 · 12:04 ET"
        title="Backtests"
        meta={`${RUNS.length} runs of ${new Set(RUNS.map((r) => r.strategyId)).size} strategies · two years each · benchmark SPY`}
        right={
          <Button variant="primary" size="md" onClick={() => ask('Draft a trend strategy on QQQ')}>
            New backtest
          </Button>
        }
      />
      <ScopeSheet scope={scope}>
        <LedgerTree
          label="Backtests"
          name="Strategy and run"
          rows={rows}
          cols={BACKTEST_COLS}
          selected={scope.key}
          onSelect={(r) => r.scope && setScope(r.scope)}
          closedAtStart={RUNS.map((r) => `bt:${r.id}`)}
        />
      </ScopeSheet>
      <Foot
        items={[
          'Backtests replay history with the same engine that runs sessions',
          'earlier runs are sample data',
          "past results don't predict future returns",
        ]}
      />
    </Page>
  );
}

const MON = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];

function Monthly({ w }: { w: Window }) {
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
  const years = [...new Set([...byMonth.values()].map((v) => v.y))];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse font-mono text-[11.5px] tabular-nums">
        <thead>
          <tr className="text-fg-3">
            <th className="w-14 py-1.5 text-left font-normal" />
            {MON.map((m, i) => (
              <th key={i} className="py-1.5 font-normal">
                {m}
              </th>
            ))}
            <th className="py-1.5 text-right font-normal">Year</th>
          </tr>
        </thead>
        <tbody>
          {years.map((y) => {
            const ms = [...byMonth.values()].filter((v) => v.y === y);
            const yr = ms.length ? ret(ms[0].first, ms[ms.length - 1].last) : 0;
            return (
              <tr key={y} className="border-t border-line">
                <td className="py-1.5 text-fg-3">{y}</td>
                {MON.map((_, m) => {
                  const v = ms.find((x) => x.m === m);
                  if (!v) return <td key={m} className="p-0.5" />;
                  const r = ret(v.first, v.last);
                  const k = Math.min(1, Math.abs(r) / 6);
                  return (
                    <td key={m} className="p-0.5">
                      <span
                        className={`block rounded-[4px] py-1.5 text-center ${r >= 0 ? 'text-gain' : 'text-loss'}`}
                        style={{
                          background: `color-mix(in srgb, rgb(var(${r >= 0 ? '--gain' : '--loss'})) ${Math.round(6 + k * 22)}%, transparent)`,
                        }}
                      >
                        {r >= 0 ? '+' : '−'}
                        {Math.abs(r).toFixed(1)}
                      </span>
                    </td>
                  );
                })}
                <td className={`py-1.5 text-right ${tone(yr)}`}>{pts(yr)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function BacktestPage() {
  const { id = '' } = useParams();
  const [scope, setScope] = useState<Scope | null>(null);
  const b = RUNS.find((x) => x.id === id);
  const s = b ? strategyById(b.strategyId) : undefined;
  const rows = useMemo(
    () =>
      backtestRows()
        .filter((r) => b && r.id.startsWith(`bt:${b.id}`))
        .map((r) => ({ ...r, depth: r.depth - 1, to: undefined })),
    [b]
  );
  if (!b || !s)
    return (
      <Page ask={false}>
        <p className="text-fg-2">This backtest could not be found.</p>
      </Page>
    );
  const w = backtestWindow(b);
  const base = rows[0]?.scope ?? ACCOUNT_SCOPE;
  const sc = scope ?? base;
  return (
    <Page ask={false} art="backtest">
      <PageHead
        eyebrow={
          <>
            <Link to="/e/backtests" className="hover:text-fg">
              Backtests
            </Link>{' '}
            / ran {b.ran}
          </>
        }
        title={`${s.name}, version ${b.version}`}
        meta={`${b.range} · $25,000 · benchmark SPY · ends at $${Math.round(25000 * (1 + b.ret)).toLocaleString('en-US')}`}
        right={
          <>
            <Button variant="primary" size="md">
              Start paper session
            </Button>
            <LinkButton to={`/e/strategies/${s.id}`} size="md">
              Open in builder
            </LinkButton>
          </>
        }
      />
      <ScopeSheet scope={sc}>
        <LedgerTree
          label={`${s.name} run`}
          name="Run and outline"
          rows={rows}
          cols={BACKTEST_COLS}
          selected={sc.key}
          onSelect={(r) => setScope(r.scope ?? base)}
        />
        {b.version !== s.version && (
          <p className="m-0 border-t border-line px-4 py-3 text-[12.5px] text-fg-3 md:px-6">
            This playground keeps the outline for the current version only.
          </p>
        )}
      </ScopeSheet>
      <div className="mt-12">
        <SectionHead
          title="Monthly returns"
          meta="Each month's change, end of month to end of month"
        />
        <Monthly w={w} />
      </div>
      <Foot
        items={[
          `Ran ${b.ran}`,
          b.range,
          'sample run for the playground',
          "past results don't predict future returns",
        ]}
      />
    </Page>
  );
}
