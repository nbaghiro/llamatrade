/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const rpc = vi.hoisted(() => ({
  listSessions: vi.fn(),
  listOrders: vi.fn(),
  listPositions: vi.fn(),
  getSession: vi.fn(),
  getOrder: vi.fn(),
  pauseSession: vi.fn(),
  resumeSession: vi.fn(),
  stopSession: vi.fn(),
  listExecutions: vi.fn(),
  listSleeves: vi.fn(),
  getStrategyPerformance: vi.fn(),
  getStrategyEquityCurve: vi.fn(),
  listStrategyPerformance: vi.fn(),
}));
const { listSessions, listOrders, listPositions } = rpc;

let tenantContext: { tenantId: string; userId: string } | undefined = {
  tenantId: 't1',
  userId: 'u1',
};
vi.mock('@llamatrade/core/net', () => ({
  tradingClient: {
    listSessions: rpc.listSessions,
    listOrders: rpc.listOrders,
    listPositions: rpc.listPositions,
    getSession: rpc.getSession,
    getOrder: rpc.getOrder,
    pauseSession: rpc.pauseSession,
    resumeSession: rpc.resumeSession,
    stopSession: rpc.stopSession,
  },
  strategyClient: { listExecutions: rpc.listExecutions },
  ledgerClient: { listSleeves: rpc.listSleeves },
  portfolioClient: {
    getStrategyPerformance: rpc.getStrategyPerformance,
    getStrategyEquityCurve: rpc.getStrategyEquityCurve,
    listStrategyPerformance: rpc.listStrategyPerformance,
  },
  authClient: {},
  getTenantContext: () => tenantContext,
}));

import { Code, ConnectError } from '@connectrpc/connect';
import type { TradingSession } from '@llamatrade/core/proto/trading_pb';
import { useFundingStore } from '@llamatrade/core/stores/funding';
import { executionFor, sleeveFor, useTradingStore } from '@llamatrade/core/stores/trading';

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
    executions: [],
    sleeves: [],
    performance: [],
    detail: null,
    detailError: null,
    order: null,
    orderError: null,
    commandPending: null,
    commandError: null,
  });
  useFundingStore.setState({ accountId: 'acct-1' });
  rpc.listExecutions.mockResolvedValue({ executions: [{ id: 'e1', sleeveId: 'sl1' }] });
  rpc.listSleeves.mockResolvedValue({ sleeves: [{ id: 'sl1', status: 2 }] });
  rpc.listStrategyPerformance.mockResolvedValue({ strategies: [{ executionId: 'e1' }] });
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
    expect(state.error).toBe('The trading service is unavailable right now.');
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

describe('sessions with their execution and sleeve', () => {
  it('loads executions and the account sleeves beside the blotter', async () => {
    await useTradingStore.getState().loadBlotter();

    const state = useTradingStore.getState();
    expect(state.executions.map((e) => e.id)).toEqual(['e1']);
    expect(state.sleeves.map((s) => s.id)).toEqual(['sl1']);
    expect(rpc.listSleeves.mock.calls[0][0].accountId).toBe('acct-1');
    expect(state.performance.map((p) => p.executionId)).toEqual(['e1']);
  });

  it('still loads the blotter when executions and sleeves fail', async () => {
    rpc.listExecutions.mockRejectedValue(new ConnectError('down'));
    rpc.listSleeves.mockRejectedValue(new ConnectError('down'));
    rpc.listStrategyPerformance.mockRejectedValue(new ConnectError('down'));

    await useTradingStore.getState().loadBlotter();

    const state = useTradingStore.getState();
    expect(state.sessions).toHaveLength(2);
    expect(state.executions).toEqual([]);
    expect(state.sleeves).toEqual([]);
    expect(state.performance).toEqual([]);
    expect(state.error).toBeNull();
  });

  it('gives both concurrent loads the sleeves while the account is still resolving', async () => {
    let finish: () => void = () => undefined;
    const pending = new Promise<void>((done) => {
      finish = () => {
        useFundingStore.setState({ accountId: 'acct-1', resolving: false });
        done();
      };
    });
    const resolveAccount = vi.fn(() => pending);
    useFundingStore.setState({ accountId: null, resolving: false, resolveAccount });
    rpc.getSession.mockResolvedValue({ session: { id: 's1', sleeveId: 'sl1' } });
    rpc.getStrategyPerformance.mockResolvedValue({ summary: null });
    rpc.getStrategyEquityCurve.mockResolvedValue({ equityCurve: [] });

    const both = Promise.all([
      useTradingStore.getState().loadBlotter(),
      useTradingStore.getState().loadSession('s1', new Date()),
    ]);
    await vi.waitFor(() => expect(resolveAccount).toHaveBeenCalled());
    finish();
    await both;

    const state = useTradingStore.getState();
    expect(state.sleeves.map((s) => s.id)).toEqual(['sl1']);
    expect(state.detail?.sleeve?.id).toBe('sl1');
  });

  it('joins on the sleeve id and never matches a session without one', () => {
    type S = Parameters<typeof executionFor>[0];
    const withSleeve = { id: 's1', sleeveId: 'sl1' } as S;
    const without = { id: 's2', sleeveId: '' } as S;
    const executions = [
      { id: 'e1', sleeveId: 'sl1' },
      { id: 'e2', sleeveId: '' },
    ] as unknown as Parameters<typeof executionFor>[1];
    expect(executionFor(withSleeve, executions)?.id).toBe('e1');
    expect(executionFor(without, executions)).toBeNull();
    expect(
      sleeveFor(withSleeve, [{ id: 'sl1' }] as unknown as Parameters<typeof sleeveFor>[1])?.id
    ).toBe('sl1');
  });
});

describe('loadSession', () => {
  beforeEach(() => {
    rpc.getSession.mockResolvedValue({ session: { id: 's1', sleeveId: 'sl1' } });
    rpc.getStrategyPerformance.mockResolvedValue({ summary: { executionId: 'e1' } });
    rpc.getStrategyEquityCurve.mockResolvedValue({ equityCurve: [{ equity: { value: '1' } }] });
  });

  it('assembles the session with its orders, execution, sleeve and today’s curve', async () => {
    const since = new Date('2026-11-13T13:30:00Z');
    await useTradingStore.getState().loadSession('s1', since);

    const { detail, detailError } = useTradingStore.getState();
    expect(detailError).toBeNull();
    expect(detail?.execution?.id).toBe('e1');
    expect(detail?.sleeve?.id).toBe('sl1');
    expect(detail?.performance?.executionId).toBe('e1');
    expect(detail?.curve).toHaveLength(1);
    expect(listOrders.mock.calls[0][0].sessionId).toBe('s1');
    const req = rpc.getStrategyEquityCurve.mock.calls[0][0];
    expect(req.executionId).toBe('e1');
    expect(req.timeRange.start.seconds).toBe(BigInt(since.getTime() / 1000));
  });

  it('skips performance reads when no execution matches', async () => {
    rpc.getSession.mockResolvedValue({ session: { id: 's1', sleeveId: '' } });

    await useTradingStore.getState().loadSession('s1', new Date());

    expect(rpc.getStrategyPerformance).not.toHaveBeenCalled();
    expect(useTradingStore.getState().detail?.curve).toEqual([]);
  });

  it('reports a missing session', async () => {
    rpc.getSession.mockRejectedValue(new ConnectError('nope', Code.NotFound));

    await useTradingStore.getState().loadSession('s9', new Date());

    expect(useTradingStore.getState().detailError).toMatch(/could not be found/);
    expect(useTradingStore.getState().detailLoading).toBe(false);
  });
});

describe('loadOrder', () => {
  it('loads one order and reports a missing one', async () => {
    rpc.getOrder.mockResolvedValueOnce({ order: { id: 'o1' } });
    await useTradingStore.getState().loadOrder('o1');
    expect(useTradingStore.getState().order?.id).toBe('o1');

    rpc.getOrder.mockResolvedValueOnce({});
    await useTradingStore.getState().loadOrder('o2');
    expect(useTradingStore.getState().order).toBeNull();
    expect(useTradingStore.getState().orderError).toMatch(/could not be found/);
  });
});

describe('runCommand', () => {
  it.each([
    ['pause', 'pauseSession'],
    ['resume', 'resumeSession'],
    ['stop', 'stopSession'],
  ] as const)('%s calls %s and swaps in the returned session', async (command, method) => {
    useTradingStore.setState({
      sessions: [{ id: 's1', isActive: true }] as unknown as TradingSession[],
    });
    rpc[method].mockResolvedValue({ session: { id: 's1', isActive: false } });

    const ok = await useTradingStore.getState().runCommand('s1', command);

    expect(ok).toBe(true);
    expect(rpc[method]).toHaveBeenCalledWith({ context: tenantContext, sessionId: 's1' });
    expect(useTradingStore.getState().sessions[0].isActive).toBe(false);
    expect(useTradingStore.getState().commandPending).toBeNull();
  });

  it('keeps the service reason when a command is refused', async () => {
    rpc.pauseSession.mockRejectedValue(
      new ConnectError('Only active sessions can be paused', Code.FailedPrecondition)
    );

    const ok = await useTradingStore.getState().runCommand('s1', 'pause');

    expect(ok).toBe(false);
    expect(useTradingStore.getState().commandError).toBe('Only active sessions can be paused');
  });

  it('ignores a second command while one is pending', async () => {
    useTradingStore.setState({ commandPending: 'stop' });

    expect(await useTradingStore.getState().runCommand('s1', 'pause')).toBe(false);
    expect(rpc.pauseSession).not.toHaveBeenCalled();
  });
});
