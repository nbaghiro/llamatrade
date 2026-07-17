import { ConnectError } from '@connectrpc/connect';
import { create } from 'zustand';

import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { strategyClient, tradingClient } from '../net';

import { getTenantContext } from '../net';
import { useFundingStore } from './funding';

/** number → proto Decimal (cents-precise string). */
function toDecimal(value: number): { value: string } {
  return { value: value.toFixed(2) };
}

export interface DeployResult {
  executionId: string;
  /** True when a live paper runner actually started. */
  live: boolean;
  /** Set when the sleeve funded but starting the runner failed (e.g. broker keys). */
  liveError: string | null;
}

interface DeployState {
  deploying: boolean;
  error: string | null;
  /**
   * Deploy a strategy: carve `allocation` out of free cash into its own sleeve,
   * then optionally attach the live paper runner.
   *
   * Funding and going live fail independently — a funded sleeve is a real,
   * durable deployment even if the broker rejects the session, so a live failure
   * is reported as `liveError` rather than failing the whole deploy.
   */
  deploy: (args: {
    strategyId: string;
    strategyName: string;
    allocation: number;
    goLive: boolean;
  }) => Promise<DeployResult | null>;
  clearError: () => void;
}

export const useDeployStore = create<DeployState>((set) => ({
  deploying: false,
  error: null,

  deploy: async ({ strategyId, strategyName, allocation, goLive }) => {
    const funding = useFundingStore.getState();
    const credentialsId = funding.paperCredentialId;
    if (!credentialsId) {
      set({ error: 'Connect Alpaca paper keys before deploying.' });
      return null;
    }
    if (!Number.isFinite(allocation) || allocation <= 0) {
      set({ error: 'Enter an allocation greater than $0.' });
      return null;
    }
    if (allocation > funding.unallocatedCash) {
      set({ error: 'Allocation is more than your free cash — add funds first.' });
      return null;
    }

    set({ deploying: true, error: null });
    const context = getTenantContext();
    let executionId: string;
    try {
      const created = await strategyClient.createExecution({
        context,
        strategyId,
        version: 0, // current
        mode: ExecutionMode.PAPER,
        allocatedCapital: toDecimal(allocation),
        credentialsId,
      });
      executionId = created.execution?.id ?? '';
      if (!executionId) throw new Error('No execution returned.');
      // Funds the sleeve (allocate_capital) and marks the execution running.
      await strategyClient.startExecution({ context, executionId });
    } catch (e) {
      set({
        deploying: false,
        error: e instanceof ConnectError ? e.message : 'Could not deploy this strategy.',
      });
      return null;
    }

    let live = false;
    let liveError: string | null = null;
    if (goLive) {
      try {
        await tradingClient.startSession({
          context,
          strategyId,
          strategyVersion: 0,
          name: `${strategyName} (paper)`,
          mode: ExecutionMode.PAPER,
          credentialsId,
          symbols: [],
          executionId,
        });
        live = true;
      } catch (e) {
        liveError = e instanceof ConnectError ? e.message : 'Could not start paper trading.';
      }
    }

    set({ deploying: false });
    // The sleeve consumed free cash either way — refresh what's allocatable.
    void useFundingStore.getState().resolveAccount();
    return { executionId, live, liveError };
  },

  clearError: () => set({ error: null }),
}));
