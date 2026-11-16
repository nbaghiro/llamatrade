import {
  DASHBOARD_PERIODS,
  useDashboardStore,
  type DashboardPeriod,
} from '@llamatrade/core/stores/dashboard';
import { LineChart as LineIcon } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';

import { formatPct } from '../../lib/format';
import { isSessionOpen } from '../../lib/marketClock';
import { LineChart } from '../charts';
import { AsOfLabel, EmptyState, Money, Pct, Segmented } from '../ui';

import { equityWindow } from './equity';
import { MarketsPanel } from './MarketsPanel';

type Tab = 'portfolio' | 'markets';

const TABS = [
  { key: 'portfolio' as const, label: 'Portfolio' },
  { key: 'markets' as const, label: 'Markets' },
];

const RANGE_LABEL: Record<DashboardPeriod, string> = {
  '1W': '1W',
  '1M': '1M',
  '3M': '3M',
  '1Y': '1Y',
  ALL: 'All',
};

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const shortDate = (d: Date) => `${MONTHS[d.getMonth()]} ${d.getDate()}`;
const clock = (d: Date) => d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });

function Kv({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-3 border-b border-line py-[7px] text-[12.5px] last:border-b-0">
      <span className="text-fg-2">{label}</span>
      {children}
    </div>
  );
}

function Legend({ bench, view }: { bench: string; view: ReturnType<typeof equityWindow> }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1 text-[11.5px] text-fg-2">
      <span className="inline-flex items-center gap-1.5">
        <i aria-hidden="true" className="inline-block w-3.5 border-t-2 border-accent" />
        Account
      </span>
      {view?.bench && (
        <span className="inline-flex items-center gap-1.5">
          <i
            aria-hidden="true"
            className="inline-block w-3.5 border-t-[1.5px] border-dashed border-fg-3"
          />
          {bench}
        </span>
      )}
      {view && (
        <span className="num text-fg-3">
          {formatPct(view.accountReturn, { signed: true })}
          {view.benchReturn !== null &&
            ` vs ${bench} ${formatPct(view.benchReturn, { signed: true })}`}
        </span>
      )}
    </div>
  );
}

function NoHistory({ connected }: { connected: boolean | null }) {
  return (
    <EmptyState
      icon={LineIcon}
      title="No equity history yet"
      body={
        connected
          ? "Your account's equity appears here once your first paper session runs. The Markets tab shows any symbol's price in the meantime."
          : "Your account's equity appears here once Alpaca is connected and a session runs. The Markets tab shows any symbol's price in the meantime."
      }
      className="min-h-[232px] content-center"
    />
  );
}

function ChartTabs({ tab, onTab }: { tab: Tab; onTab: (tab: Tab) => void }) {
  return <Segmented<Tab> label="Chart" value={tab} onChange={onTab} options={TABS} />;
}

/** The account's equity line against its benchmark, with a range control and a Markets tab. */
function Chart({
  compact,
  tab,
  onTab,
}: {
  compact: boolean;
  tab: Tab;
  onTab: ((tab: Tab) => void) | null;
}) {
  const portfolioCurve = useDashboardStore((s) => s.portfolioCurve);
  const benchmarkCurve = useDashboardStore((s) => s.benchmarkCurve);
  const bench = useDashboardStore((s) => s.benchmarkSymbol) || 'SPY';
  const period = useDashboardStore((s) => s.selectedPeriod);
  const setPeriod = useDashboardStore((s) => s.setPeriod);
  const connected = useDashboardStore((s) => s.brokerConnected);
  const view = useMemo(
    () => equityWindow(portfolioCurve, benchmarkCurve, period),
    [portfolioCurve, benchmarkCurve, period]
  );
  const height = compact ? 232 : 250;

  const showRange = tab === 'portfolio' && view !== null;
  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] content-start gap-1.5">
      {(onTab || showRange) && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          {tab === 'portfolio' && !compact ? <Legend bench={bench} view={view} /> : <span />}
          <div className="flex flex-wrap items-center gap-2">
            {onTab && <ChartTabs tab={tab} onTab={onTab} />}
            {showRange && (
              <Segmented<DashboardPeriod>
                label="Range"
                value={period}
                onChange={setPeriod}
                options={DASHBOARD_PERIODS.map((p) => ({ key: p, label: RANGE_LABEL[p] }))}
              />
            )}
          </div>
        </div>
      )}
      {tab === 'markets' ? (
        <MarketsPanel height={height - 40} />
      ) : view ? (
        <LineChart
          label={`Account return against ${bench}`}
          dates={view.dates}
          series={[
            { values: view.account, kind: 'main', area: true },
            ...(view.bench ? [{ values: view.bench, kind: 'bench' as const }] : []),
          ]}
          height={height}
          zeroLine={0}
          yFormat={(v) => `${v.toFixed(1)}%`}
          xFormat={shortDate}
          tooltip={(i) => (
            <>
              {shortDate(view.dates[i])} · Account{' '}
              {formatPct(view.account[i] / 100, { signed: true })}
              {view.bench && ` · ${bench} ${formatPct(view.bench[i] / 100, { signed: true })}`}
            </>
          )}
        />
      ) : (
        <NoHistory connected={connected} />
      )}
    </div>
  );
}

function Figures() {
  const totalEquity = useDashboardStore((s) => s.totalEquity);
  const totalReturn = useDashboardStore((s) => s.totalReturn);
  const freeCash = useDashboardStore((s) => s.freeCash);
  const deployed = useDashboardStore((s) => s.deployedValue);
  const live = useDashboardStore((s) => s.liveStrategiesCount);
  const positions = useDashboardStore((s) => s.openPositionsCount);
  const curve = useDashboardStore((s) => s.portfolioCurve);
  const lastChange = useDashboardStore((s) => s.lastChange);
  const asOf = useDashboardStore((s) => s.equityAsOf);

  const first = curve[0] ? new Date(curve[0].timestamp) : null;
  const sinceReturn = curve.length > 1 ? curve[curve.length - 1].value / 100 : null;
  const open = isSessionOpen(new Date());

  return (
    <div>
      <span className="text-[11px] font-medium text-fg-3">Total equity · paper</span>
      <Money
        value={totalEquity}
        className="my-0.5 block text-[30px] tracking-[-0.03em] md:text-[30px]"
      />
      {lastChange && (
        <div className="text-[12.5px]">
          <Money value={lastChange.amount} pnl /> · <Pct value={lastChange.fraction} pnl />
          <span className="text-fg-3">
            {' '}
            since {lastChange.since ? shortDate(lastChange.since) : 'the last snapshot'}
          </span>
        </div>
      )}
      {open ? (
        asOf && <div className="text-[12px] text-fg-3">Last snapshot {clock(asOf)}</div>
      ) : (
        <AsOfLabel />
      )}
      <div className="mt-3.5">
        <Kv label="Total return">
          <Money value={totalReturn} pnl />
        </Kv>
        {first && sinceReturn !== null && (
          <Kv label={`Since ${shortDate(first)}`}>
            <Pct value={sinceReturn} pnl />
          </Kv>
        )}
        <Kv label="Free cash">
          <Money value={freeCash} />
        </Kv>
        <Kv label="Deployed">
          <Money value={deployed} />
        </Kv>
        <Kv label="Sessions">
          <span className="num">
            {live} · {positions} position{positions === 1 ? '' : 's'}
          </span>
        </Kv>
      </div>
    </div>
  );
}

/** Home's main panel: the account figures beside one large equity chart. */
export function EquityPanel() {
  const [tab, setTab] = useState<Tab>('portfolio');
  return (
    <section
      aria-label="Account equity"
      className="grid grid-cols-[minmax(0,1fr)] overflow-hidden rounded-panel border border-line bg-panel md:grid-cols-[280px_minmax(0,1fr)]"
    >
      <div className="border-b border-line p-4 md:border-b-0 md:border-r">
        <Figures />
      </div>
      <div className="p-3 md:px-4 md:py-3">
        <Chart compact={false} tab={tab} onTab={setTab} />
      </div>
    </section>
  );
}

/** First-visit version: no figures yet, just the chart area with its empty state and Markets tab. */
export function EquityPanelEmpty() {
  const [tab, setTab] = useState<Tab>('portfolio');
  return (
    <section
      aria-label="Total equity"
      className="overflow-hidden rounded-panel border border-line bg-panel"
    >
      <div className="flex min-h-[42px] items-center justify-between gap-2.5 border-b border-line px-3.5 py-1.5 text-[12.5px]">
        <b className="font-semibold">Total equity</b>
        <ChartTabs tab={tab} onTab={setTab} />
      </div>
      <div className="p-3">
        <Chart compact tab={tab} onTab={null} />
      </div>
    </section>
  );
}
