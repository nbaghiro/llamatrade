/**
 * Portfolio + dashboard read store — the real backend, same RPCs the web app uses.
 * Powers both the Portfolio (Book) screen and the Home dashboard:
 *   ListPortfolios · ListStrategyPerformance · GetPerformance (equity curve)
 *   · ListTransactions (activity) · GetMarketStatus.
 */
import { ConnectError } from '@connectrpc/connect';
import { create } from 'zustand';

import { num } from '@llamatrade/core/format';
import { MarketStatus } from '@llamatrade/core/proto/market_data_pb';
import type { Portfolio, StrategyPerformanceSummary, Transaction } from '@llamatrade/core/proto/portfolio_pb';
import { marketDataClient, portfolioClient } from '../net/clients';
import { tenantContext } from './auth';

export function errorMessage(e: unknown): string {
  if (e instanceof ConnectError) return e.rawMessage || e.message;
  return e instanceof Error ? e.message : 'Something went wrong';
}

interface PortfolioState {
  portfolio: Portfolio | null;
  strategies: StrategyPerformanceSummary[];
  equityCurve: number[];
  benchmarkCurve: number[];
  transactions: Transaction[];
  marketStatus: MarketStatus | null;
  loading: boolean;
  refreshing: boolean;
  loaded: boolean;
  error: string | null;
  fetch: (opts?: { refresh?: boolean }) => Promise<void>;
}

export const usePortfolioStore = create<PortfolioState>((set) => ({
  portfolio: null,
  strategies: [],
  equityCurve: [],
  benchmarkCurve: [],
  transactions: [],
  marketStatus: null,
  loading: false,
  refreshing: false,
  loaded: false,
  error: null,

  fetch: async (opts) => {
    const context = tenantContext();
    if (!context) {
      set({ error: 'Not signed in.', loading: false, refreshing: false });
      return;
    }
    set(opts?.refresh ? { refreshing: true, error: null } : { loading: true, error: null });
    try {
      const [p, s, market] = await Promise.all([
        portfolioClient.listPortfolios({ context }),
        portfolioClient.listStrategyPerformance({ context }),
        marketDataClient.getMarketStatus({}).catch(() => null),
      ]);
      const portfolio = p.portfolios[0] ?? null;

      // Equity curve + activity depend on the portfolio; degrade per-section.
      // GetPerformance returns metrics only (no time series), so the portfolio
      // curve is the sum of per-sleeve equity curves (real seeded snapshots),
      // sharing one benchmark line — the same source the web app uses.
      let equityCurve: number[] = [];
      let benchmarkCurve: number[] = [];
      let transactions: Transaction[] = [];
      if (portfolio) {
        const deployed = s.strategies.filter((x) => num(x.allocatedCapital) > 0);
        const [curves, txns] = await Promise.all([
          Promise.all(
            deployed.map((x) =>
              portfolioClient
                .getStrategyEquityCurve({ context, executionId: x.executionId, benchmarkSymbol: 'SPY', sampleIntervalMinutes: 0 })
                .catch(() => null),
            ),
          ),
          portfolioClient
            .listTransactions({ context, portfolioId: portfolio.id, pagination: { page: 1, pageSize: 15 } })
            .then((r) => r.transactions)
            .catch(() => []),
        ]);

        const agg = new Map<number, number>();
        let bench: { ts: number; v: number }[] = [];
        for (const c of curves) {
          if (!c) continue;
          for (const pt of c.equityCurve) {
            const ts = Number(pt.timestamp?.seconds ?? 0);
            if (ts) agg.set(ts, (agg.get(ts) ?? 0) + num(pt.equity));
          }
          if (bench.length === 0 && c.benchmark?.equityCurve?.length) {
            bench = c.benchmark.equityCurve.map((pt) => ({ ts: Number(pt.timestamp?.seconds ?? 0), v: num(pt.equity) }));
          } else if (bench.length === 0) {
            const withBench = c.equityCurve.filter((pt) => num(pt.benchmarkValue) > 0);
            if (withBench.length > 1) bench = withBench.map((pt) => ({ ts: Number(pt.timestamp?.seconds ?? 0), v: num(pt.benchmarkValue) }));
          }
        }
        const tsSorted = [...agg.keys()].sort((a, b) => a - b);
        equityCurve = tsSorted.map((ts) => agg.get(ts) ?? 0);
        benchmarkCurve = bench.length > 1 ? bench.sort((a, b) => a.ts - b.ts).map((b) => b.v) : [];
        transactions = txns;
      }

      set({
        portfolio,
        strategies: s.strategies,
        equityCurve,
        benchmarkCurve,
        transactions,
        marketStatus: market?.status ?? null,
        loading: false,
        refreshing: false,
        loaded: true,
      });
    } catch (e) {
      set({ error: errorMessage(e), loading: false, refreshing: false });
    }
  },
}));
