/**
 * Trading Store
 * Paper sessions with what the console needs beside them: the order blotter, positions,
 * each session's strategy execution and ledger sleeve, one session's detail, one order,
 * and the pause, resume and stop actions.
 */

import { Code, ConnectError } from "@connectrpc/connect";
import { create } from "zustand";

import type { Sleeve } from "@llamatrade/core/proto/ledger_pb";
import type {
  StrategyEquityPoint,
  StrategyPerformanceSummary,
} from "@llamatrade/core/proto/portfolio_pb";
import type { StrategyExecution } from "@llamatrade/core/proto/strategy_pb";
import {
  OrderSide,
  OrderType,
  TimeInForce,
  type Order,
  type Position,
  type TradingSession,
} from "@llamatrade/core/proto/trading_pb";
import {
  ledgerClient,
  portfolioClient,
  strategyClient,
  tradingClient,
} from "../net";

import { getTenantContext } from "../net";
import { useFundingStore } from "./funding";

export type SessionCommand = "pause" | "resume" | "stop";

export interface SessionDetail {
  session: TradingSession;
  positions: Position[];
  orders: Order[];
  execution: StrategyExecution | null;
  sleeve: Sleeve | null;
  performance: StrategyPerformanceSummary | null;
  /** Equity points since `since`, from the portfolio service. */
  curve: StrategyEquityPoint[];
  /** SPY on the same dates, rebased to the curve's start; empty when unavailable. */
  benchmark: StrategyEquityPoint[];
}

/** One execution's equity since it started, with SPY on the same dates. */
export interface SessionCurve {
  points: StrategyEquityPoint[];
  benchmark: StrategyEquityPoint[];
}

export interface PlaceOrderInput {
  sessionId: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  strategyId?: string;
  sleeveId?: string;
}

interface TradingState {
  sessions: TradingSession[];
  orders: Order[];
  positions: Position[];
  executions: StrategyExecution[];
  sleeves: Sleeve[];
  /** Portfolio figures per strategy execution (current value, period returns). */
  performance: StrategyPerformanceSummary[];
  loading: boolean;
  loaded: boolean;
  error: string | null;

  detail: SessionDetail | null;
  detailLoading: boolean;
  detailError: string | null;

  order: Order | null;
  orderLoading: boolean;
  orderError: string | null;

  commandPending: SessionCommand | null;
  commandError: string | null;

  /** Equity curves keyed by execution id; filled by `loadCurves`. */
  curves: Record<string, SessionCurve>;
  curvesLoaded: boolean;

  placing: boolean;
  placeError: string | null;

  loadBlotter: () => Promise<void>;
  loadSession: (sessionId: string, since: Date) => Promise<void>;
  loadOrder: (orderId: string) => Promise<void>;
  runCommand: (sessionId: string, command: SessionCommand) => Promise<boolean>;
  /** Every loaded execution's curve since it started; one failure leaves that curve out. */
  loadCurves: () => Promise<void>;
  /** A market day order through the session's own checks; the new order, or null. */
  placeOrder: (input: PlaceOrderInput) => Promise<Order | null>;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof ConnectError) {
    switch (error.code) {
      case Code.Unauthenticated:
        return "Please log in to view trading activity.";
      case Code.PermissionDenied:
        return "You don't have permission to view this trading activity.";
      case Code.NotFound:
        return "This session or order could not be found.";
      case Code.Unavailable:
        return "The trading service is unavailable right now.";
      default:
        return error.message || "Something went wrong.";
    }
  }
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

/** Runs a best-effort read; any failure, sync or async, yields the fallback. */
async function optional<T>(read: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await read();
  } catch {
    return fallback;
  }
}

async function paperAccountId(): Promise<string | null> {
  if (!useFundingStore.getState().accountId)
    await useFundingStore.getState().resolveAccount();
  return useFundingStore.getState().accountId;
}

async function readSleeves(): Promise<Sleeve[]> {
  const context = getTenantContext();
  const accountId = await paperAccountId();
  if (!accountId) return [];
  const res = await ledgerClient.listSleeves({ context, accountId });
  return res.sleeves;
}

async function readExecutions(): Promise<StrategyExecution[]> {
  const context = getTenantContext();
  const res = await strategyClient.listExecutions({
    context,
    pagination: { page: 1, pageSize: 100 },
  });
  return res.executions;
}

/** The execution behind a session, matched on the sleeve both carry. */
export function executionFor(
  session: TradingSession,
  executions: readonly StrategyExecution[],
): StrategyExecution | null {
  if (!session.sleeveId) return null;
  return executions.find((e) => e.sleeveId === session.sleeveId) ?? null;
}

export function sleeveFor(
  session: TradingSession,
  sleeves: readonly Sleeve[],
): Sleeve | null {
  if (!session.sleeveId) return null;
  return sleeves.find((s) => s.id === session.sleeveId) ?? null;
}

const COMMAND_ERROR: Record<SessionCommand, string> = {
  pause: "The session could not be paused.",
  resume: "The session could not be resumed.",
  stop: "The session could not be stopped.",
};

export const useTradingStore = create<TradingState>((set, get) => ({
  sessions: [],
  orders: [],
  positions: [],
  executions: [],
  sleeves: [],
  performance: [],
  loading: false,
  loaded: false,
  error: null,

  detail: null,
  detailLoading: false,
  detailError: null,

  order: null,
  orderLoading: false,
  orderError: null,

  commandPending: null,
  commandError: null,

  curves: {},
  curvesLoaded: false,

  placing: false,
  placeError: null,

  loadBlotter: async () => {
    const context = getTenantContext();
    if (!context) {
      set({
        error: "Please log in to view trading activity.",
        loading: false,
        loaded: true,
      });
      return;
    }

    set({ loading: true, error: null });
    try {
      const [sessionsRes, ordersRes, executions, sleeves, performance] =
        await Promise.all([
          tradingClient.listSessions({
            context,
            pagination: { page: 1, pageSize: 100 },
          }),
          tradingClient.listOrders({
            context,
            pagination: { page: 1, pageSize: 200 },
          }),
          optional(readExecutions, [] as StrategyExecution[]),
          optional(readSleeves, [] as Sleeve[]),
          optional(
            () =>
              portfolioClient
                .listStrategyPerformance({
                  context,
                  pagination: { page: 1, pageSize: 100 },
                })
                .then((r) => r.strategies),
            [] as StrategyPerformanceSummary[],
          ),
        ]);

      // ListPositions requires a session_id; one failure doesn't blank the rest.
      const positionLists = await Promise.all(
        sessionsRes.sessions.map((s) =>
          tradingClient
            .listPositions({ context, sessionId: s.id })
            .then((r) => r.positions)
            .catch(() => [] as Position[]),
        ),
      );

      set({
        sessions: sessionsRes.sessions,
        orders: ordersRes.orders,
        positions: positionLists.flat(),
        executions,
        sleeves,
        performance,
        loading: false,
        loaded: true,
      });
    } catch (error) {
      set({ error: getErrorMessage(error), loading: false, loaded: true });
    }
  },

  loadSession: async (sessionId, since) => {
    const context = getTenantContext();
    if (!context) {
      set({
        detailError: "Please log in to view this session.",
        detailLoading: false,
      });
      return;
    }
    set((state) => ({
      detailLoading: true,
      detailError: null,
      detail: state.detail?.session.id === sessionId ? state.detail : null,
    }));
    try {
      const [sessionRes, positions, orders, executions, sleeves] =
        await Promise.all([
          tradingClient.getSession({ context, sessionId }),
          optional(
            () =>
              tradingClient
                .listPositions({ context, sessionId })
                .then((r) => r.positions),
            [] as Position[],
          ),
          optional(
            () =>
              tradingClient
                .listOrders({
                  context,
                  sessionId,
                  pagination: { page: 1, pageSize: 200 },
                })
                .then((r) => r.orders),
            [] as Order[],
          ),
          optional(readExecutions, [] as StrategyExecution[]),
          optional(readSleeves, [] as Sleeve[]),
        ]);
      const session = sessionRes.session;
      if (!session) throw new Error("This session could not be found.");
      const execution = executionFor(session, executions);
      const [performance, curve] = execution
        ? await Promise.all([
            optional(
              () =>
                portfolioClient
                  .getStrategyPerformance({
                    context,
                    executionId: execution.id,
                  })
                  .then((r) => r.summary ?? null),
              null,
            ),
            optional(
              () =>
                portfolioClient
                  .getStrategyEquityCurve({
                    context,
                    executionId: execution.id,
                    timeRange: {
                      start: {
                        seconds: BigInt(Math.floor(since.getTime() / 1000)),
                        nanos: 0,
                      },
                      end: {
                        seconds: BigInt(Math.floor(Date.now() / 1000)),
                        nanos: 0,
                      },
                    },
                    sampleIntervalMinutes: 5,
                    benchmarkSymbol: "SPY",
                  })
                  .then((r) => ({
                    points: r.equityCurve,
                    benchmark: r.benchmark?.equityCurve ?? [],
                  })),
              { points: [], benchmark: [] } as SessionCurve,
            ),
          ])
        : [null, { points: [], benchmark: [] } as SessionCurve];
      set({
        detail: {
          session,
          positions,
          orders,
          execution,
          sleeve: sleeveFor(session, sleeves),
          performance,
          curve: curve.points,
          benchmark: curve.benchmark,
        },
        detailLoading: false,
      });
    } catch (error) {
      set({ detailError: getErrorMessage(error), detailLoading: false });
    }
  },

  loadOrder: async (orderId) => {
    const context = getTenantContext();
    if (!context) {
      set({
        orderError: "Please log in to view this order.",
        orderLoading: false,
      });
      return;
    }
    set({ orderLoading: true, orderError: null, order: null });
    try {
      const res = await tradingClient.getOrder({ context, orderId });
      if (!res.order) throw new Error("This order could not be found.");
      set({ order: res.order, orderLoading: false });
    } catch (error) {
      set({ orderError: getErrorMessage(error), orderLoading: false });
    }
  },

  runCommand: async (sessionId, command) => {
    const context = getTenantContext();
    if (!context || get().commandPending) return false;
    set({ commandPending: command, commandError: null });
    try {
      const req = { context, sessionId };
      const res =
        command === "pause"
          ? await tradingClient.pauseSession(req)
          : command === "resume"
            ? await tradingClient.resumeSession(req)
            : await tradingClient.stopSession(req);
      const updated = res.session;
      let sleeveError: string | null = null;
      if (command === "stop") {
        const state = get();
        const session =
          updated ??
          state.sessions.find((s) => s.id === sessionId) ??
          state.detail?.session;
        const execution =
          (session && executionFor(session, state.executions)) ??
          (state.detail?.session.id === sessionId
            ? state.detail.execution
            : null);
        // Stopping the execution is what closes the sleeve: holdings to Unmanaged, cash to Unallocated.
        if (execution) {
          try {
            await strategyClient.stopExecution({
              context,
              executionId: execution.id,
              reason: "session stopped",
            });
          } catch {
            sleeveError =
              "The session stopped, but its sleeve couldn't be closed, so its holdings and cash stay in the sleeve for now.";
          }
        }
      }
      set((state) => ({
        commandError: sleeveError,
        commandPending: null,
        sessions: updated
          ? state.sessions.map((s) => (s.id === updated.id ? updated : s))
          : state.sessions,
        detail:
          updated && state.detail?.session.id === updated.id
            ? { ...state.detail, session: updated }
            : state.detail,
      }));
      return true;
    } catch (error) {
      set({
        commandPending: null,
        commandError:
          error instanceof ConnectError && error.rawMessage
            ? error.rawMessage
            : COMMAND_ERROR[command],
      });
      return false;
    }
  },

  loadCurves: async () => {
    const context = getTenantContext();
    if (!context) return;
    const ids = [
      ...new Set(
        get()
          .sessions.map((s) => executionFor(s, get().executions)?.id)
          .filter((id): id is string => Boolean(id)),
      ),
    ];
    const results = await Promise.all(
      ids.map((executionId) =>
        optional(
          () =>
            portfolioClient
              .getStrategyEquityCurve({
                context,
                executionId,
                benchmarkSymbol: "SPY",
                sampleIntervalMinutes: 0,
              })
              .then((r): [string, SessionCurve] => [
                executionId,
                {
                  points: r.equityCurve,
                  benchmark: r.benchmark?.equityCurve ?? [],
                },
              ]),
          null,
        ),
      ),
    );
    set((state) => ({
      curves: {
        ...state.curves,
        ...Object.fromEntries(
          results.filter((r): r is [string, SessionCurve] => r !== null),
        ),
      },
      curvesLoaded: true,
    }));
  },

  placeOrder: async ({
    sessionId,
    symbol,
    side,
    quantity,
    strategyId,
    sleeveId,
  }) => {
    const context = getTenantContext();
    if (!context || get().placing) return null;
    if (!Number.isFinite(quantity) || quantity <= 0) {
      set({ placeError: "Enter a quantity greater than zero." });
      return null;
    }
    set({ placing: true, placeError: null });
    try {
      const res = await tradingClient.submitOrder({
        context,
        sessionId,
        clientOrderId: crypto.randomUUID(),
        symbol,
        side: side === "buy" ? OrderSide.BUY : OrderSide.SELL,
        type: OrderType.MARKET,
        timeInForce: TimeInForce.DAY,
        quantity: { value: String(quantity) },
        strategyId: strategyId ?? "",
        sleeveId: sleeveId ?? "",
      });
      const order = res.order ?? null;
      set((state) => ({
        placing: false,
        orders: order ? [order, ...state.orders] : state.orders,
      }));
      return order;
    } catch (error) {
      set({
        placing: false,
        placeError:
          error instanceof ConnectError && error.rawMessage
            ? error.rawMessage
            : "The order could not be placed.",
      });
      return null;
    }
  },
}));
