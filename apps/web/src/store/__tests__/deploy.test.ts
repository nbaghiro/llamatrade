/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { createExecution, startExecution, startSession } = vi.hoisted(() => ({
  createExecution: vi.fn(),
  startExecution: vi.fn(),
  startSession: vi.fn(),
}));

let tenantContext: { tenantId: string; userId: string } | undefined = {
  tenantId: 't1',
  userId: 'u1',
};
vi.mock('@llamatrade/core/net', () => ({
  strategyClient: { createExecution, startExecution },
  tradingClient: { startSession },
  authClient: { listAlpacaCredentials: vi.fn().mockResolvedValue({ credentials: [] }) },
  ledgerClient: { getOrCreateAccount: vi.fn(), depositFunds: vi.fn() },
  getTenantContext: () => tenantContext,
}));

import { ConnectError } from '@connectrpc/connect';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { useDeployStore, validateDeploy } from '@llamatrade/core/stores/deploy';
import { useFundingStore } from '@llamatrade/core/stores/funding';

const ARGS = {
  strategyId: 'strat-1',
  strategyName: 'Momentum',
  allocation: 1000,
  goLive: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  tenantContext = { tenantId: 't1', userId: 'u1' };
  useDeployStore.setState({ deploying: false, error: null });
  useFundingStore.setState({ paperCredentialId: 'paper-1', unallocatedCash: 5000 });
  createExecution.mockResolvedValue({ execution: { id: 'exec-1' } });
  startExecution.mockResolvedValue({});
  startSession.mockResolvedValue({ session: { id: 'sess-1' } });
});

describe('deploy guards', () => {
  it('refuses without a paper credential', async () => {
    useFundingStore.setState({ paperCredentialId: null });

    const result = await useDeployStore.getState().deploy(ARGS);

    expect(result).toBeNull();
    expect(createExecution).not.toHaveBeenCalled();
    expect(useDeployStore.getState().error).toMatch(/paper keys/i);
  });

  it.each([0, -5, Number.NaN])('refuses a non-positive allocation (%s)', async (allocation) => {
    const result = await useDeployStore.getState().deploy({ ...ARGS, allocation });

    expect(result).toBeNull();
    expect(createExecution).not.toHaveBeenCalled();
  });

  it('refuses to allocate more than free cash', async () => {
    useFundingStore.setState({ unallocatedCash: 100 });

    const result = await useDeployStore.getState().deploy({ ...ARGS, allocation: 101 });

    expect(result).toBeNull();
    expect(createExecution).not.toHaveBeenCalled();
    expect(useDeployStore.getState().error).toMatch(/unallocated cash/i);
  });

  it('allows allocating exactly the free balance', async () => {
    useFundingStore.setState({ unallocatedCash: 1000 });

    const result = await useDeployStore.getState().deploy({ ...ARGS, allocation: 1000 });

    expect(result?.executionId).toBe('exec-1');
  });
});

describe('validateDeploy', () => {
  const base = { allocation: 1000, unallocatedCash: 5000, hasPaperCredential: true };

  it('accepts an amount within unallocated cash, including all of it', () => {
    expect(validateDeploy(base)).toBeNull();
    expect(validateDeploy({ ...base, allocation: 5000 })).toBeNull();
  });

  it('asks for paper keys first', () => {
    expect(validateDeploy({ ...base, hasPaperCredential: false })).toMatch(/paper keys/i);
  });

  it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY])('refuses %s', (allocation) => {
    expect(validateDeploy({ ...base, allocation })).toMatch(/greater than \$0/);
  });

  it('compares at cent precision so float noise never blocks the full balance', () => {
    expect(validateDeploy({ ...base, allocation: 0.1 + 0.2, unallocatedCash: 0.3 })).toBeNull();
    expect(validateDeploy({ ...base, allocation: 5000.01 })).toMatch(/unallocated cash/i);
  });
});

describe('deploy funding path', () => {
  it('deploys the version it was given', async () => {
    await useDeployStore.getState().deploy({ ...ARGS, strategyVersion: 3, goLive: true });

    expect(createExecution).toHaveBeenCalledWith(expect.objectContaining({ version: 3 }));
    expect(startSession).toHaveBeenCalledWith(expect.objectContaining({ strategyVersion: 3 }));
  });

  it('creates then starts the execution with a cents-precise allocation', async () => {
    const result = await useDeployStore.getState().deploy(ARGS);

    expect(createExecution).toHaveBeenCalledWith(
      expect.objectContaining({
        strategyId: 'strat-1',
        mode: ExecutionMode.PAPER,
        allocatedCapital: { value: '1000.00' },
        credentialsId: 'paper-1',
      })
    );
    expect(startExecution).toHaveBeenCalledWith(expect.objectContaining({ executionId: 'exec-1' }));
    expect(result).toEqual({
      executionId: 'exec-1',
      sessionId: null,
      live: false,
      liveError: null,
    });
    expect(useDeployStore.getState().deploying).toBe(false);
  });

  it('fails the deploy when CreateExecution returns no id', async () => {
    createExecution.mockResolvedValue({ execution: undefined });

    const result = await useDeployStore.getState().deploy(ARGS);

    expect(result).toBeNull();
    expect(startExecution).not.toHaveBeenCalled();
    expect(useDeployStore.getState().deploying).toBe(false);
  });

  it('reports a refused StartExecution and never goes live', async () => {
    startExecution.mockRejectedValue(new ConnectError('insufficient free cash'));

    const result = await useDeployStore.getState().deploy({ ...ARGS, goLive: true });

    expect(result).toBeNull();
    expect(startSession).not.toHaveBeenCalled();
    expect(useDeployStore.getState().error).toContain('insufficient free cash');
  });
});

describe('deploy live path', () => {
  it('starts a paper session when goLive is set', async () => {
    const result = await useDeployStore.getState().deploy({ ...ARGS, goLive: true });

    expect(startSession).toHaveBeenCalledWith(
      expect.objectContaining({
        strategyId: 'strat-1',
        executionId: 'exec-1',
        mode: ExecutionMode.PAPER,
        credentialsId: 'paper-1',
      })
    );
    expect(result).toEqual({
      executionId: 'exec-1',
      sessionId: 'sess-1',
      live: true,
      liveError: null,
    });
  });

  it('keeps the funded deployment when only the live session fails', async () => {
    startSession.mockRejectedValue(new ConnectError('broker rejected the keys'));

    const result = await useDeployStore.getState().deploy({ ...ARGS, goLive: true });

    // The sleeve is funded and durable: a live failure must not read as no deploy.
    expect(result?.executionId).toBe('exec-1');
    expect(result?.live).toBe(false);
    expect(result?.liveError).toContain('broker rejected the keys');
    expect(useDeployStore.getState().error).toBeNull();
  });

  it('refreshes free cash after a deploy consumes it', async () => {
    const resolveAccount = vi.fn().mockResolvedValue(undefined);
    useFundingStore.setState({ resolveAccount });

    await useDeployStore.getState().deploy(ARGS);

    expect(resolveAccount).toHaveBeenCalled();
  });
});
