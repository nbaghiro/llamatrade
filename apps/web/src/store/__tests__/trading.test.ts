/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { listSessions, listOrders, listPositions } = vi.hoisted(() => ({
  listSessions: vi.fn(),
  listOrders: vi.fn(),
  listPositions: vi.fn(),
}));

let tenantContext: { tenantId: string; userId: string } | undefined = {
  tenantId: 't1',
  userId: 'u1',
};
vi.mock('@llamatrade/core/net', () => ({
  tradingClient: { listSessions, listOrders, listPositions },
  getTenantContext: () => tenantContext,
}));

import { Code, ConnectError } from '@connectrpc/connect';
import { useTradingStore } from '@llamatrade/core/stores/trading';

beforeEach(() => {
  vi.clearAllMocks();
  tenantContext = { tenantId: 't1', userId: 'u1' };
  useTradingStore.setState({
    sessions: [],
    orders: [],
    positions: [],
    loading: false,
    loaded: false,
    error: null,
  });
  listSessions.mockResolvedValue({ sessions: [{ id: 's1' }, { id: 's2' }] });
  listOrders.mockResolvedValue({ orders: [{ id: 'o1' }] });
  listPositions.mockImplementation(({ sessionId }: { sessionId: string }) =>
    Promise.resolve({ positions: [{ symbol: `SYM-${sessionId}` }] })
  );
});

describe('loadBlotter', () => {
  it('loads sessions, the tenant-wide order blotter, and per-session positions', async () => {
    await useTradingStore.getState().loadBlotter();

    const state = useTradingStore.getState();
    expect(state.sessions).toHaveLength(2);
    expect(state.orders).toHaveLength(1);
    expect(state.positions.map((p) => p.symbol)).toEqual(['SYM-s1', 'SYM-s2']);
    expect(state.loading).toBe(false);
    expect(state.loaded).toBe(true);
    expect(state.error).toBeNull();
  });

  it('requests positions per session, since ListPositions requires a session id', async () => {
    await useTradingStore.getState().loadBlotter();

    expect(listPositions).toHaveBeenCalledTimes(2);
    for (const call of listPositions.mock.calls) {
      expect(call[0].sessionId).toBeTruthy();
    }
  });

  it('asks for orders across all sessions rather than per session', async () => {
    await useTradingStore.getState().loadBlotter();

    expect(listOrders).toHaveBeenCalledTimes(1);
    expect(listOrders.mock.calls[0][0].sessionId).toBeUndefined();
  });

  it('keeps the blotter when one session’s positions fail', async () => {
    listPositions.mockImplementation(({ sessionId }: { sessionId: string }) =>
      sessionId === 's1'
        ? Promise.reject(new ConnectError('boom'))
        : Promise.resolve({ positions: [{ symbol: 'OK' }] })
    );

    await useTradingStore.getState().loadBlotter();

    const state = useTradingStore.getState();
    // Degrading per session is deliberate: one bad session must not blank the page.
    expect(state.positions.map((p) => p.symbol)).toEqual(['OK']);
    expect(state.orders).toHaveLength(1);
    expect(state.error).toBeNull();
  });

  it('reports a failure and still marks the load finished', async () => {
    listSessions.mockRejectedValue(new ConnectError('down', Code.Unavailable));

    await useTradingStore.getState().loadBlotter();

    const state = useTradingStore.getState();
    expect(state.error).toBe('Trading service is temporarily unavailable');
    expect(state.loading).toBe(false);
    expect(state.loaded).toBe(true);
  });

  it.each([
    [Code.Unauthenticated, /log in/i],
    [Code.PermissionDenied, /permission/i],
  ])('maps %s to a readable message', async (code, expected) => {
    listSessions.mockRejectedValue(new ConnectError('raw', code));

    await useTradingStore.getState().loadBlotter();

    expect(useTradingStore.getState().error).toMatch(expected);
  });

  it('refuses to call the service when signed out', async () => {
    tenantContext = undefined;

    await useTradingStore.getState().loadBlotter();

    expect(listSessions).not.toHaveBeenCalled();
    expect(useTradingStore.getState().error).toMatch(/log in/i);
    expect(useTradingStore.getState().loaded).toBe(true);
  });
});
