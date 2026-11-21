/** Maps the core stores onto the Home model's plain shapes, and loads what Home and Portfolio read. */

import { ExecutionMode, ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { MarketStatus } from '@llamatrade/core/proto/market_data_pb';
import { OrderSide, OrderStatus, type Order } from '@llamatrade/core/proto/trading_pb';
import { useDashboardStore, type DashboardStrategy } from '@llamatrade/core/stores/dashboard';
import { readLiveAccount, useFundingStore } from '@llamatrade/core/stores/funding';
import { usePortfolioStore } from '@llamatrade/core/stores/portfolio';
import { executionFor, useTradingStore } from '@llamatrade/core/stores/trading';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { create } from 'zustand';

import type { FillIn, FrozenIn, RejectedIn, RowState, SessionIn } from './model';

function seconds(ts: { seconds: bigint } | undefined): number | null {
  return ts?.seconds ? Number(ts.seconds) * 1000 : null;
}

function rowState(status: ExecutionStatus, frozen: boolean): RowState {
  if (frozen && status !== ExecutionStatus.STOPPED) return 'frozen';
  switch (status) {
    case ExecutionStatus.RUNNING:
      return 'running';
    case ExecutionStatus.PENDING:
      return 'waiting';
    case ExecutionStatus.PAUSED:
      return 'paused';
    case ExecutionStatus.ERROR:
      return 'error';
    default:
      return 'stopped';
  }
}

/** Filled orders as fills, newest first. */
export function fillsOf(orders: readonly Order[]): FillIn[] {
  return orders
    .filter((o) => o.status === OrderStatus.FILLED && o.filledAt)
    .map((o) => ({
      id: o.id,
      t: seconds(o.filledAt) ?? 0,
      symbol: o.symbol,
      side: o.side === OrderSide.SELL ? ('sell' as const) : ('buy' as const),
      qty: Number(o.filledQuantity?.value ?? o.quantity?.value ?? 0),
      price: Number(o.averageFillPrice?.value ?? 0),
      strategyId: o.strategyId,
      sessionId: o.sessionId,
    }))
    .sort((a, b) => b.t - a.t);
}

interface LiveCashState {
  liveCash: number | null;
  /** True once a read has finished. */
  liveRead: boolean;
  loadLive: () => Promise<void>;
}

/** The live account's free cash; null when there is no live account or it couldn't be read. */
export const useLiveCash = create<LiveCashState>()((set) => ({
  liveCash: null,
  liveRead: false,
  loadLive: async () => {
    try {
      const live = await readLiveAccount();
      set({ liveCash: live ? live.unallocatedCash : null, liveRead: true });
    } catch {
      set({ liveCash: null, liveRead: true });
    }
  },
}));

/** Everything Home and Portfolio read, loaded together; `refresh` reloads it all. */
export function useHomeData() {
  const dash = useDashboardStore();
  const trading = useTradingStore();
  const portfolio = usePortfolioStore();
  const paperCashFallback = useFundingStore((s) => (s.resolved ? s.unallocatedCash : null));
  const { liveCash, loadLive } = useLiveCash();
  const [refreshing, setRefreshing] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(async () => {
    setNow(Date.now());
    await Promise.all([
      useDashboardStore.getState().fetchDashboard(),
      useTradingStore.getState().loadBlotter(),
      usePortfolioStore.getState().fetchPortfolio(),
      useLiveCash.getState().loadLive(),
    ]);
  }, []);

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await load();
    } finally {
      setRefreshing(false);
    }
  }, [load]);

  const fills = useMemo(() => fillsOf(trading.orders), [trading.orders]);

  const sessions: SessionIn[] = useMemo(() => {
    const frozen = new Set((dash.frozenSleeves ?? []).map((f) => f.executionId));
    return dash.strategies.map((s: DashboardStrategy) => {
      const ts = trading.sessions.find((x) => {
        const ex = executionFor(x, trading.executions);
        return ex ? ex.id === s.id : false;
      });
      const sleeve = portfolio.sleeves.find((x) => x.executionId === s.id);
      return {
        id: s.id,
        strategyId: s.strategyId,
        sessionId: ts?.id ?? null,
        sleeveId: sleeve?.sleeveId ?? ts?.sleeveId ?? null,
        name: s.name,
        mode: s.mode === ExecutionMode.LIVE ? 'live' : 'paper',
        state: rowState(s.status, frozen.has(s.id) || (sleeve?.frozen ?? false)),
        value: s.currentValue,
        dayReturnPct: Number.isFinite(s.dayReturn) ? s.dayReturn * 100 : null,
        allocated: s.allocatedCapital,
        equity: s.equity.map((p) => ({ t: new Date(p.timestamp).getTime(), v: p.value })).filter((p) => Number.isFinite(p.t)),
        startedAt: s.startedAt?.getTime() ?? seconds(ts?.startedAt),
        endedAt: seconds(ts?.endedAt),
        rebalance: sleeve?.rebalance || s.descriptor,
      };
    });
  }, [dash.strategies, dash.frozenSleeves, trading.sessions, trading.executions, portfolio.sleeves]);

  const frozen: FrozenIn[] | null = dash.frozenSleeves;
  const rejected: RejectedIn[] | null = useMemo(
    () =>
      dash.rejectedOrders?.map((o) => ({
        id: o.id,
        symbol: o.symbol,
        side: o.side === OrderSide.SELL ? 'sell' : 'buy',
        quantity: o.quantity,
        message: o.message,
        t: o.at?.getTime() ?? null,
        sessionId: o.sessionId,
      })) ?? null,
    [dash.rejectedOrders],
  );

  const marketOpen =
    dash.marketStatus === null || dash.marketStatus === MarketStatus.UNSPECIFIED ? null : dash.marketStatus === MarketStatus.OPEN;

  return {
    now,
    loaded: dash.loaded,
    loading: dash.loading && !dash.loaded,
    error: dash.error,
    refreshing,
    refresh,
    sessions,
    fills,
    frozen,
    rejected,
    totalEquity: dash.totalEquity,
    dayPnl: dash.dayPnl,
    dayPnlPercent: dash.dayPnlPercent,
    benchmark: dash.benchmarkCurve,
    equityAsOf: dash.equityAsOf,
    strategyCount: dash.strategyCount,
    completedBacktestCount: dash.completedBacktestCount,
    marketOpen,
    marketNextOpen: dash.marketNextOpen,
    marketNextClose: dash.marketNextClose,
    paperCash: portfolio.unallocated ?? paperCashFallback,
    liveCash,
    loadLive,
  };
}

export type HomeData = ReturnType<typeof useHomeData>;
