// Dashboard store: composes the Dashboard view from the Connect APIs directly; self-contained (no dependency on other stores).

import { create } from 'zustand';

import type { CurvePoint } from '../components/dashboard/chart';
import {
  fmtCurrency,
  fmtDateShort,
  fmtQty,
  fmtSignedCurrency,
  fmtSignedFraction,
} from '../components/dashboard/format';
import { BacktestStatus, type BacktestRun } from '../generated/proto/backtest_pb';
import { ExecutionStatus, type Decimal, type Timestamp } from '../generated/proto/common_pb';
import { MarketStatus } from '../generated/proto/market_data_pb';
import {
  TransactionType,
  type GetStrategyEquityCurveResponse,
  type StrategyEquityPoint,
  type Transaction,
} from '../generated/proto/portfolio_pb';
import type { Strategy } from '../generated/proto/strategy_pb';
import {
  backtestClient,
  marketDataClient,
  portfolioClient,
  strategyClient,
} from '../services/grpc-client';

import { getTenantContext } from './auth';

export { ExecutionStatus, MarketStatus };

export type DashboardPeriod = '1W' | '1M' | '3M' | '1Y' | 'ALL';
export const DASHBOARD_PERIODS: DashboardPeriod[] = ['1W', '1M', '3M', '1Y', 'ALL'];

export interface DashboardStrategy {
  id: string; // execution_id
  strategyId: string;
  name: string;
  color: string;
  descriptor: string; // template/timeframe descriptor for the meta line
  allocatedCapital: number;
  positionsCount: number;
  status: ExecutionStatus;
  isLive: boolean;
  dayReturn: number; // 1-day return as a decimal fraction
  returns: Record<DashboardPeriod, number>; // decimal fractions (0.12 = 12%)
  curve: CurvePoint[]; // cumulative % return series for the sparkline
}

export type ActivityKind = 'buy' | 'sell' | 'dividend' | 'backtest';

export interface DashboardActivity {
  id: string;
  kind: ActivityKind;
  title: string;
  subtitle: string;
  at: Date | null;
}

export type MarketStatusSource = 'rpc' | 'derived';

interface DashboardState {
  // Account KPIs
  totalEquity: number;
  dayPnl: number;
  dayPnlPercent: number;
  totalReturn: number;
  totalReturnPercent: number;
  freeCash: number;
  freeCashPercent: number;
  deployedValue: number;
  liveStrategiesCount: number;
  openPositionsCount: number;
  atAllTimeHigh: boolean;

  // Series + panels
  strategies: DashboardStrategy[];
  portfolioCurve: CurvePoint[];
  benchmarkCurve: CurvePoint[];
  benchmarkSymbol: string;
  activity: DashboardActivity[];

  // Market clock
  marketStatus: MarketStatus | null;
  marketNextOpen: Date | null;
  marketNextClose: Date | null;
  marketStatusSource: MarketStatusSource;

  // UI + async
  selectedPeriod: DashboardPeriod;
  loading: boolean;
  error: string | null;

  fetchDashboard: () => Promise<void>;
  fetchMarketStatus: () => Promise<void>;
  setPeriod: (period: DashboardPeriod) => void;
  clearError: () => void;
}

const STRATEGY_COLORS = ['#0f7a34', '#1a1aff', '#ff4d1c', '#c81e1e', '#6b2fb3', '#0e8ba0'];

// ---- proto → local conversion ----

function toNumber(d: Decimal | undefined): number {
  return d?.value ? parseFloat(d.value) : 0;
}

function toISO(ts: Timestamp | undefined): string {
  if (!ts?.seconds) return new Date().toISOString();
  return new Date(Number(ts.seconds) * 1000).toISOString();
}

function toDate(ts: Timestamp | undefined): Date | null {
  if (!ts?.seconds) return null;
  return new Date(Number(ts.seconds) * 1000);
}

/** Cumulative-% return series from an absolute-equity curve (rebased to point 0). */
function toPercentCurve(points: StrategyEquityPoint[]): CurvePoint[] {
  if (points.length === 0) return [];
  const base = toNumber(points[0].equity);
  return points.map((p) => ({
    timestamp: toISO(p.timestamp),
    value: base !== 0 ? (toNumber(p.equity) / base - 1) * 100 : 0,
  }));
}

/**
 * Blend per-strategy absolute-equity curves into one account-level % series,
 * right-anchored to "now" (mirrors the portfolio page's aggregate line): a leg
 * with less history contributes its allocated capital before it began.
 */
function buildPortfolioCurve(
  curves: (GetStrategyEquityCurveResponse | null)[],
  strategies: DashboardStrategy[]
): CurvePoint[] {
  const series: { equity: number[]; timestamps: string[]; baseline: number }[] = [];
  curves.forEach((curve, i) => {
    const pts = curve?.equityCurve;
    if (!pts || pts.length === 0) return;
    const equity = pts.map((p) => toNumber(p.equity));
    series.push({
      equity,
      timestamps: pts.map((p) => toISO(p.timestamp)),
      baseline: strategies[i].allocatedCapital || equity[0],
    });
  });
  if (series.length === 0) return [];

  const maxLen = Math.max(...series.map((s) => s.equity.length));
  const totalBaseline = series.reduce((sum, s) => sum + s.baseline, 0);
  const longest = series.find((s) => s.equity.length === maxLen) ?? series[0];

  const out: CurvePoint[] = [];
  for (let j = 0; j < maxLen; j++) {
    let sum = 0;
    for (const s of series) {
      const pos = s.equity.length - maxLen + j;
      sum += pos >= 0 ? s.equity[pos] : s.baseline;
    }
    out.push({
      timestamp: longest.timestamps[j] ?? new Date().toISOString(),
      value: totalBaseline > 0 ? (sum / totalBaseline - 1) * 100 : 0,
    });
  }
  return out;
}

/** Short type descriptor for the strategy row. Template slug > timeframe > symbols. */
function descriptorFor(strategy: Strategy | undefined): string {
  if (!strategy) return '';
  const tpl = strategy.templateId?.trim();
  const isSlug = tpl && /[a-z]/i.test(tpl) && !/^[0-9a-f-]{20,}$/i.test(tpl);
  if (isSlug) return tpl.replace(/_/g, '-').toLowerCase();
  if (strategy.timeframe) return `${strategy.timeframe} bars`;
  if (strategy.symbols.length) return `${strategy.symbols.length} symbols`;
  return '';
}

function transactionActivity(t: Transaction, strategyNames: Map<string, string>): DashboardActivity | null {
  const symbol = t.symbol || '';
  const qty = toNumber(t.quantity);
  const price = toNumber(t.price);
  const amount = toNumber(t.amount);
  const at = toDate(t.timestamp);
  const strategyName = strategyNames.get(t.referenceId);

  switch (t.type) {
    case TransactionType.BUY:
    case TransactionType.SELL: {
      const kind: ActivityKind = t.type === TransactionType.BUY ? 'buy' : 'sell';
      return {
        id: t.id,
        kind,
        title: `${fmtQty(qty)} ${symbol} @ ${fmtCurrency(price, 2)}`,
        subtitle: t.description || strategyName || (kind === 'buy' ? 'Filled' : 'Rebalance'),
        at,
      };
    }
    case TransactionType.DIVIDEND:
      return {
        id: t.id,
        kind: 'dividend',
        title: `${fmtSignedCurrency(Math.abs(amount), 2)} dividend · ${symbol}`,
        subtitle: t.description || 'Cash credited',
        at,
      };
    default:
      return null;
  }
}

function backtestActivity(run: BacktestRun, strategyNames: Map<string, string>): DashboardActivity {
  const metrics = run.results?.metrics;
  const name = strategyNames.get(run.strategyId) || 'Strategy';
  const ret = metrics ? fmtSignedFraction(toNumber(metrics.totalReturn), 1) : '';
  const sharpe = metrics ? toNumber(metrics.sharpeRatio).toFixed(2) : '';
  const stats = [ret, sharpe ? `${sharpe} SR` : ''].filter(Boolean).join(' · ');
  const at = toDate(run.completedAt) ?? toDate(run.createdAt);
  return {
    id: `bt-${run.id}`,
    kind: 'backtest',
    title: stats ? `${name} ✓ ${stats}` : `${name} ✓ Complete`,
    subtitle: at ? `Backtest complete · ${fmtDateShort(at)}` : 'Backtest complete',
    at,
  };
}

const EMPTY = {
  totalEquity: 0,
  dayPnl: 0,
  dayPnlPercent: 0,
  totalReturn: 0,
  totalReturnPercent: 0,
  freeCash: 0,
  freeCashPercent: 0,
  deployedValue: 0,
  liveStrategiesCount: 0,
  openPositionsCount: 0,
  atAllTimeHigh: false,
  strategies: [] as DashboardStrategy[],
  portfolioCurve: [] as CurvePoint[],
  benchmarkCurve: [] as CurvePoint[],
  benchmarkSymbol: '',
  activity: [] as DashboardActivity[],
};

export const useDashboardStore = create<DashboardState>((set) => ({
  ...EMPTY,
  marketStatus: null,
  marketNextOpen: null,
  marketNextClose: null,
  marketStatusSource: 'derived',
  selectedPeriod: '1M',
  loading: false,
  error: null,

  fetchDashboard: async () => {
    set({ loading: true, error: null });

    const context = getTenantContext();
    if (!context) {
      set({ ...EMPTY, loading: false, error: null });
      return;
    }

    try {
      const benchmarkSymbol = 'SPY';

      // Deployed strategies (executions) drive the whole page; fetch them first
      // so the equity-curve / metric fan-out can key off their execution ids.
      const [perfResponse, strategyList] = await Promise.all([
        portfolioClient.listStrategyPerformance({ context, pagination: { page: 1, pageSize: 50 } }),
        strategyClient
          .listStrategies({ context, pagination: { page: 1, pageSize: 100 } })
          .catch(() => null),
      ]);

      const strategyById = new Map<string, Strategy>(
        (strategyList?.strategies ?? []).map((s) => [s.id, s])
      );
      const strategyNames = new Map<string, string>(
        (strategyList?.strategies ?? []).map((s) => [s.id, s.name])
      );

      const strategies: DashboardStrategy[] = perfResponse.strategies.map((s, i) => {
        strategyNames.set(s.strategyId, s.strategyName);
        return {
          id: s.executionId,
          strategyId: s.strategyId,
          name: s.strategyName,
          color: s.color || STRATEGY_COLORS[i % STRATEGY_COLORS.length],
          descriptor: descriptorFor(strategyById.get(s.strategyId)),
          allocatedCapital: toNumber(s.allocatedCapital),
          positionsCount: s.positionsCount,
          status: s.status,
          isLive: s.status === ExecutionStatus.RUNNING,
          dayReturn: toNumber(s.returns?.return1d) / 100,
          returns: {
            '1W': toNumber(s.returns?.return1w) / 100,
            '1M': toNumber(s.returns?.return1m) / 100,
            '3M': toNumber(s.returns?.return3m) / 100,
            '1Y': toNumber(s.returns?.return1y) / 100,
            ALL: toNumber(s.returns?.returnAll) / 100,
          },
          curve: [],
        };
      });

      // Fan out (all non-blocking): account summary, per-strategy equity curves,
      // completed backtests, and the market clock.
      const [portfolioList, curves, backtestList, marketRes] = await Promise.all([
        portfolioClient
          .listPortfolios({ context, pagination: { page: 1, pageSize: 1 } })
          .catch(() => null),
        Promise.all(
          strategies.map((s) =>
            portfolioClient
              .getStrategyEquityCurve({
                context,
                executionId: s.id,
                benchmarkSymbol,
                sampleIntervalMinutes: 0,
              })
              .catch(() => null)
          )
        ),
        backtestClient
          .listBacktests({ context, strategyId: '', pagination: { page: 1, pageSize: 50 } })
          .catch(() => null),
        marketDataClient.getMarketStatus({}).catch(() => null),
      ]);

      // Attach per-strategy curves; pick the first benchmark series we can find.
      let benchmarkCurve: CurvePoint[] = [];
      const currentValues: number[] = [];
      curves.forEach((curve, i) => {
        if (!curve) return;
        strategies[i].curve = toPercentCurve(curve.equityCurve);
        const pts = curve.equityCurve;
        if (pts.length > 0) currentValues[i] = toNumber(pts[pts.length - 1].equity);
        if (benchmarkCurve.length === 0 && curve.benchmark?.equityCurve?.length) {
          benchmarkCurve = toPercentCurve(curve.benchmark.equityCurve);
        }
      });

      // Deployed = capital marked to market; fall back to allocated when a curve
      // is missing so the aggregate never under-reports the book.
      const deployedValue = strategies.reduce(
        (sum, s, i) => sum + (currentValues[i] || s.allocatedCapital),
        0
      );
      const totalAllocated = strategies.reduce((sum, s) => sum + s.allocatedCapital, 0);

      const summary = portfolioList?.portfolios[0];
      const summaryTotal = summary ? toNumber(summary.totalValue) : 0;
      const summaryCash = summary ? toNumber(summary.cashBalance) : 0;

      const freeCash = summaryCash || (summaryTotal > deployedValue ? summaryTotal - deployedValue : 0);
      const totalEquity = summaryTotal || deployedValue + freeCash;
      const freeCashPercent = totalEquity > 0 ? (freeCash / totalEquity) * 100 : 0;

      const derivedReturn = deployedValue - totalAllocated;
      const totalReturn = (summary && toNumber(summary.totalReturn)) || derivedReturn;
      const totalReturnPercent =
        (summary && toNumber(summary.totalReturnPercent)) ||
        (totalAllocated > 0 ? (derivedReturn / totalAllocated) * 100 : 0);

      const derivedDayPnl = strategies.reduce(
        (sum, s, i) => sum + (currentValues[i] || s.allocatedCapital) * s.dayReturn,
        0
      );
      const dayPnl = (summary && toNumber(summary.dayReturn)) || derivedDayPnl;
      const dayPnlPercent =
        (summary && toNumber(summary.dayReturnPercent)) ||
        (totalEquity - dayPnl > 0 ? (dayPnl / (totalEquity - dayPnl)) * 100 : 0);

      const liveStrategiesCount = strategies.filter((s) => s.isLive).length;
      const openPositionsCount = strategies.reduce((sum, s) => sum + s.positionsCount, 0);

      const portfolioCurve = buildPortfolioCurve(curves, strategies);
      const atAllTimeHigh =
        portfolioCurve.length > 1 &&
        portfolioCurve[portfolioCurve.length - 1].value >=
          Math.max(...portfolioCurve.map((p) => p.value));

      // Activity feed: recent transactions (fills + dividends) merged with the
      // most recent completed backtests, newest first.
      const transactions = summary
        ? await portfolioClient
            .listTransactions({
              context,
              portfolioId: summary.id,
              pagination: { page: 1, pageSize: 15 },
            })
            .then((r) => r.transactions)
            .catch(() => [])
        : [];

      const completedRuns = (backtestList?.backtests ?? [])
        .filter((b) => b.status === BacktestStatus.COMPLETED)
        .sort(
          (a, b) =>
            (toDate(b.completedAt) ?? toDate(b.createdAt) ?? new Date(0)).getTime() -
            (toDate(a.completedAt) ?? toDate(a.createdAt) ?? new Date(0)).getTime()
        )
        .slice(0, 3);

      // ListBacktests omits results, so hydrate the few we show for metrics.
      const hydratedRuns = await Promise.all(
        completedRuns.map((b) =>
          backtestClient
            .getBacktest({ context, backtestId: b.id })
            .then((r) => r.backtest ?? b)
            .catch(() => b)
        )
      );

      const activity: DashboardActivity[] = [
        ...transactions
          .map((t) => transactionActivity(t, strategyNames))
          .filter((a): a is DashboardActivity => a !== null),
        ...hydratedRuns.map((b) => backtestActivity(b, strategyNames)),
      ]
        .sort((a, b) => (b.at?.getTime() ?? 0) - (a.at?.getTime() ?? 0))
        .slice(0, 6);

      set({
        totalEquity,
        dayPnl,
        dayPnlPercent,
        totalReturn,
        totalReturnPercent,
        freeCash,
        freeCashPercent,
        deployedValue,
        liveStrategiesCount,
        openPositionsCount,
        atAllTimeHigh,
        strategies,
        portfolioCurve,
        benchmarkCurve,
        benchmarkSymbol,
        activity,
        loading: false,
      });

      if (marketRes) {
        set({
          marketStatus: marketRes.status,
          marketNextOpen: toDate(marketRes.nextOpen),
          marketNextClose: toDate(marketRes.nextClose),
          marketStatusSource:
            marketRes.status === MarketStatus.UNSPECIFIED ? 'derived' : 'rpc',
        });
      } else {
        set({ marketStatus: null, marketStatusSource: 'derived' });
      }
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to load dashboard',
        loading: false,
      });
    }
  },

  fetchMarketStatus: async () => {
    try {
      const res = await marketDataClient.getMarketStatus({});
      set({
        marketStatus: res.status,
        marketNextOpen: toDate(res.nextOpen),
        marketNextClose: toDate(res.nextClose),
        marketStatusSource: res.status === MarketStatus.UNSPECIFIED ? 'derived' : 'rpc',
      });
    } catch {
      set({ marketStatus: null, marketNextOpen: null, marketNextClose: null, marketStatusSource: 'derived' });
    }
  },

  setPeriod: (period) => set({ selectedPeriod: period }),

  clearError: () => set({ error: null }),
}));
