/**
 * Trading Store
 * Reads the tenant's live/paper trading sessions, their orders (blotter) and
 * any open positions from the TradingService. Read-only: session lifecycle and
 * order submission happen elsewhere (deployment flow / strategy engine).
 */

import { Code, ConnectError } from '@connectrpc/connect';
import { create } from 'zustand';

import type { Order, Position, TradingSession } from '../generated/proto/trading_pb';
import { tradingClient } from '../services/grpc-client';

import { getTenantContext } from './auth';

interface TradingState {
  sessions: TradingSession[];
  orders: Order[];
  positions: Position[];
  loading: boolean;
  loaded: boolean;
  error: string | null;
  loadBlotter: () => Promise<void>;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof ConnectError) {
    switch (error.code) {
      case Code.Unauthenticated:
        return 'Please log in to view trading activity';
      case Code.PermissionDenied:
        return 'You do not have permission to view this trading activity';
      case Code.Unavailable:
        return 'Trading service is temporarily unavailable';
      default:
        return error.message || 'An error occurred';
    }
  }
  if (error instanceof Error) return error.message;
  return 'An unexpected error occurred';
}

export const useTradingStore = create<TradingState>((set) => ({
  sessions: [],
  orders: [],
  positions: [],
  loading: false,
  loaded: false,
  error: null,

  loadBlotter: async () => {
    const context = getTenantContext();
    if (!context) {
      set({ error: 'Please log in to view trading activity', loading: false, loaded: true });
      return;
    }

    set({ loading: true, error: null });
    try {
      // Sessions + the full tenant order blotter (empty session_id = all sessions).
      const [sessionsRes, ordersRes] = await Promise.all([
        tradingClient.listSessions({ context, pagination: { page: 1, pageSize: 100 } }),
        tradingClient.listOrders({ context, pagination: { page: 1, pageSize: 200 } }),
      ]);

      // Open positions are queried per session (ListPositions requires a session_id).
      // Degrade per-session so one failure doesn't blank the whole blotter.
      const positionLists = await Promise.all(
        sessionsRes.sessions.map((s) =>
          tradingClient
            .listPositions({ context, sessionId: s.id })
            .then((r) => r.positions)
            .catch(() => [] as Position[])
        )
      );

      set({
        sessions: sessionsRes.sessions,
        orders: ordersRes.orders,
        positions: positionLists.flat(),
        loading: false,
        loaded: true,
      });
    } catch (error) {
      set({ error: getErrorMessage(error), loading: false, loaded: true });
    }
  },
}));
