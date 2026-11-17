/**
 * Portfolio store: the paper account as the ledger records it. Strategy performance gives each
 * sleeve's value and holdings; the ledger gives sleeve status, sleeve cash and unallocated cash.
 */

import { create } from "zustand";

import {
  ExecutionMode,
  ExecutionStatus,
  type Timestamp,
} from "@llamatrade/core/proto/common_pb";
import {
  SleeveStatus,
  SleeveType,
  type Lot,
  type Sleeve,
} from "@llamatrade/core/proto/ledger_pb";
import type { StrategyPerformanceSummary } from "@llamatrade/core/proto/portfolio_pb";
import type { Position as ProtoPosition } from "@llamatrade/core/proto/trading_pb";
import { fixedTargets } from "../agent/structure";
import { num } from "../format";
import {
  getTenantContext,
  ledgerClient,
  portfolioClient,
  strategyClient,
} from "../net";
import { freeCash, useFundingStore } from "./funding";

export { ExecutionStatus, SleeveStatus };

export interface Holding {
  symbol: string;
  qty: number;
  price: number;
  avgEntryPrice: number;
  marketValue: number;
  unrealizedPnl: number;
}

export interface SleeveSummary {
  executionId: string;
  strategyId: string;
  name: string;
  executionStatus: ExecutionStatus;
  /** Runs on the live Alpaca account rather than paper. */
  live: boolean;
  /** Ledger sleeve id; null when the ledger couldn't be read. */
  sleeveId: string | null;
  frozen: boolean;
  allocatedCapital: number;
  value: number;
  /** Today's return in percent, as the backend reports it. */
  dayReturnPct: number;
  startedAt: Date | null;
  /** "monthly", "quarterly" and so on; empty when unknown. */
  rebalance: string;
  holdings: Holding[];
  /** Target weight per symbol, as fractions, when the strategy's weights are fixed; else empty. */
  targets: Record<string, number>;
  /** Ledger cash balance inside the sleeve; null when the ledger couldn't be read. */
  cash: number | null;
}

export interface LedgerLot {
  symbol: string;
  qty: number;
  avgPrice: number;
  openedAt: Date | null;
}

export interface SleeveDetail extends SleeveSummary {
  sleeveId: string;
  sleeveName: string;
  lots: LedgerLot[];
  /** Open quantity per symbol as the ledger records it. */
  ledgerQty: Record<string, number>;
}

interface PortfolioState {
  sleeves: SleeveSummary[];
  /** Unallocated free cash from the ledger; null when the ledger couldn't be read. */
  unallocated: number | null;
  /** The account summary's total, used only when the ledger figure is missing. */
  summaryTotal: number;
  loading: boolean;
  /** True once a load has finished, so refreshes keep the page instead of showing skeletons. */
  loaded: boolean;
  error: string | null;

  sleeve: SleeveDetail | null;
  sleeveLoading: boolean;
  sleeveError: string | null;

  fetchPortfolio: () => Promise<void>;
  fetchSleeve: (sleeveId: string) => Promise<void>;
  clearError: () => void;
}

function toDate(ts: Timestamp | undefined): Date | null {
  return ts?.seconds ? new Date(Number(ts.seconds) * 1000) : null;
}

function mapHolding(p: ProtoPosition): Holding {
  return {
    symbol: p.symbol,
    qty: num(p.quantity),
    price: num(p.currentPrice),
    avgEntryPrice: num(p.averageEntryPrice),
    marketValue: num(p.marketValue),
    unrealizedPnl: num(p.unrealizedPnl),
  };
}

/** Open ledger quantity per symbol, summed across lots. */
export function ledgerQuantities(
  lots: readonly LedgerLot[],
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const lot of lots) out[lot.symbol] = (out[lot.symbol] ?? 0) + lot.qty;
  return out;
}

function mapLots(lots: readonly Lot[]): LedgerLot[] {
  return lots
    .filter((l) => l.isOpen)
    .map((l) => ({
      symbol: l.symbol,
      qty: num(l.qty),
      avgPrice: num(l.avgPrice),
      openedAt: toDate(l.openedAt),
    }));
}

/**
 * A sleeve belongs on the overview while it holds capital: its ledger sleeve isn't closed, or,
 * without ledger data, its execution hasn't stopped.
 */
export function isOpenSleeve(
  status: ExecutionStatus,
  sleeve: Sleeve | undefined,
): boolean {
  if (sleeve) return sleeve.status !== SleeveStatus.CLOSED;
  return status !== ExecutionStatus.STOPPED;
}

interface StrategyPlan {
  rebalance: string;
  targets: Record<string, number>;
}

const NO_PLAN: StrategyPlan = { rebalance: "", targets: {} };

function planOf(
  strategy: { rebalance: string; dslCode: string } | undefined,
): StrategyPlan {
  if (!strategy) return NO_PLAN;
  return {
    rebalance: strategy.rebalance,
    targets: fixedTargets(strategy.dslCode) ?? {},
  };
}

function summarize(
  s: StrategyPerformanceSummary,
  sleeve: Sleeve | undefined,
  plan: StrategyPlan,
): SleeveSummary {
  return {
    executionId: s.executionId,
    strategyId: s.strategyId,
    name: s.strategyName || sleeve?.name || "Strategy",
    executionStatus: s.status,
    live: s.mode === ExecutionMode.LIVE,
    sleeveId: sleeve?.id ?? null,
    frozen: sleeve?.status === SleeveStatus.FROZEN,
    allocatedCapital: num(s.allocatedCapital),
    value: num(s.currentValue),
    dayReturnPct: num(s.returns?.return1d),
    startedAt: toDate(s.startedAt),
    rebalance: plan.rebalance,
    holdings: [],
    targets: plan.targets,
    cash: sleeve?.cash ? num(sleeve.cash.balance) : null,
  };
}

async function plansById(): Promise<Record<string, StrategyPlan>> {
  const context = getTenantContext();
  const res = await strategyClient
    .listStrategies({ context, pagination: { page: 1, pageSize: 100 } })
    .catch(() => null);
  const out: Record<string, StrategyPlan> = {};
  for (const st of res?.strategies ?? []) out[st.id] = planOf(st);
  return out;
}

/** Reads the ledger's sleeves for the paper account; null when it can't be reached. */
async function ledgerSleeves(): Promise<Sleeve[] | null> {
  const funding = useFundingStore.getState();
  if (!funding.resolved || !funding.accountId) await funding.resolveAccount();
  const accountId = useFundingStore.getState().accountId;
  if (!accountId) return null;
  const res = await ledgerClient
    .listSleeves({ context: getTenantContext(), accountId })
    .catch(() => null);
  return res?.sleeves ?? null;
}

const EMPTY = {
  sleeves: [] as SleeveSummary[],
  unallocated: null,
  summaryTotal: 0,
};

export const usePortfolioStore = create<PortfolioState>((set, get) => ({
  ...EMPTY,
  loading: false,
  loaded: false,
  error: null,

  sleeve: null,
  sleeveLoading: false,
  sleeveError: null,

  fetchPortfolio: async () => {
    const context = getTenantContext();
    if (!context) {
      set({ ...EMPTY, loading: false, loaded: true, error: null });
      return;
    }
    set({ loading: true, error: null });

    try {
      const [perf, summaryList, ledger, plans] = await Promise.all([
        portfolioClient.listStrategyPerformance({
          context,
          pagination: { page: 1, pageSize: 50 },
        }),
        portfolioClient
          .listPortfolios({ context, pagination: { page: 1, pageSize: 1 } })
          .catch(() => null),
        ledgerSleeves().catch(() => null),
        plansById(),
      ]);

      const byExecution = new Map<string, Sleeve>();
      for (const sl of ledger ?? []) {
        if (sl.type === SleeveType.STRATEGY && sl.strategyExecutionId) {
          byExecution.set(sl.strategyExecutionId, sl);
        }
      }

      const open = perf.strategies.filter((s) =>
        isOpenSleeve(s.status, byExecution.get(s.executionId)),
      );
      const details = await Promise.all(
        open.map((s) =>
          portfolioClient
            .getStrategyPerformance({ context, executionId: s.executionId })
            .catch(() => null),
        ),
      );
      const sleeves = open.map((s, i) => {
        const summary = summarize(
          s,
          byExecution.get(s.executionId),
          plans[s.strategyId] ?? NO_PLAN,
        );
        summary.holdings = details[i]?.positions.map(mapHolding) ?? [];
        return summary;
      });

      const unallocatedSleeve = ledger?.find(
        (sl) => sl.type === SleeveType.UNALLOCATED,
      );
      const unallocated = ledger
        ? unallocatedSleeve
          ? freeCash(unallocatedSleeve)
          : useFundingStore.getState().unallocatedCash
        : null;
      const summary = summaryList?.portfolios[0];

      set({
        sleeves,
        unallocated,
        summaryTotal: summary ? num(summary.totalValue) : 0,
        loading: false,
        loaded: true,
      });
    } catch (error) {
      set({
        error:
          error instanceof Error ? error.message : "Failed to fetch portfolio",
        loading: false,
        loaded: true,
      });
    }
  },

  fetchSleeve: async (sleeveId) => {
    const context = getTenantContext();
    if (!context) return;
    const current = get().sleeve;
    set({
      sleeveLoading: true,
      sleeveError: null,
      sleeve: current?.sleeveId === sleeveId ? current : null,
    });

    try {
      const res = await ledgerClient.getSleeve({ context, sleeveId });
      const sl = res.sleeve;
      if (!sl) throw new Error("This sleeve could not be found.");
      const lots = mapLots(res.lots);

      const executionId = sl.strategyExecutionId;
      const perf = executionId
        ? await portfolioClient
            .getStrategyPerformance({ context, executionId })
            .catch(() => null)
        : null;
      const strategyId = perf?.summary?.strategyId ?? "";
      const strategy = strategyId
        ? await strategyClient
            .getStrategy({ context, strategyId, version: 0 })
            .catch(() => null)
        : null;

      const base: SleeveSummary = perf?.summary
        ? summarize(perf.summary, sl, planOf(strategy?.strategy))
        : {
            executionId,
            strategyId: "",
            name: sl.name || "Sleeve",
            executionStatus: ExecutionStatus.UNSPECIFIED,
            live: false,
            sleeveId: sl.id,
            frozen: sl.status === SleeveStatus.FROZEN,
            allocatedCapital: num(sl.allocatedCapital),
            value: num(sl.cash?.balance),
            dayReturnPct: 0,
            startedAt: toDate(sl.createdAt),
            rebalance: "",
            holdings: [],
            targets: {},
            cash: sl.cash ? num(sl.cash.balance) : null,
          };

      set({
        sleeve: {
          ...base,
          sleeveId: sl.id,
          sleeveName: sl.name,
          holdings: perf?.positions.map(mapHolding) ?? [],
          lots,
          ledgerQty: ledgerQuantities(lots),
        },
        sleeveLoading: false,
      });
    } catch (error) {
      set({
        sleeveLoading: false,
        sleeveError:
          error instanceof Error ? error.message : "Failed to load this sleeve",
      });
    }
  },

  clearError: () => set({ error: null }),
}));
