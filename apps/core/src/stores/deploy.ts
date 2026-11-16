import { ConnectError } from "@connectrpc/connect";
import { create } from "zustand";

import { ExecutionMode } from "@llamatrade/core/proto/common_pb";
import { strategyClient, tradingClient } from "../net";

import { getTenantContext } from "../net";
import { useFundingStore } from "./funding";

/** number → proto Decimal (cents-precise string). */
function toDecimal(value: number): { value: string } {
  return { value: value.toFixed(2) };
}

export interface DeployCheckInput {
  allocation: number;
  unallocatedCash: number;
  hasPaperCredential: boolean;
}

/** Why a deploy can't start yet, or null when it can. Amounts compare at cent precision. */
export function validateDeploy({
  allocation,
  unallocatedCash,
  hasPaperCredential,
}: DeployCheckInput): string | null {
  if (!hasPaperCredential) return "Connect Alpaca paper keys before deploying.";
  if (!Number.isFinite(allocation) || allocation <= 0)
    return "Enter an amount greater than $0.";
  const cents = (v: number) => Math.round(v * 100);
  if (cents(allocation) > cents(unallocatedCash)) {
    return "That is more than your unallocated cash. Lower the amount or add funds first.";
  }
  return null;
}

export interface DeployResult {
  executionId: string;
  /** The paper session that started, when `goLive` was set and it started. */
  sessionId: string | null;
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
    /** 0 deploys the current version. */
    strategyVersion?: number;
    allocation: number;
    goLive: boolean;
  }) => Promise<DeployResult | null>;
  clearError: () => void;
}

export const useDeployStore = create<DeployState>((set) => ({
  deploying: false,
  error: null,

  deploy: async ({
    strategyId,
    strategyName,
    strategyVersion = 0,
    allocation,
    goLive,
  }) => {
    const funding = useFundingStore.getState();
    const credentialsId = funding.paperCredentialId;
    const invalid = validateDeploy({
      allocation,
      unallocatedCash: funding.unallocatedCash,
      hasPaperCredential: credentialsId !== null,
    });
    if (invalid || !credentialsId) {
      set({ error: invalid });
      return null;
    }

    set({ deploying: true, error: null });
    const context = getTenantContext();
    let executionId: string;
    try {
      const created = await strategyClient.createExecution({
        context,
        strategyId,
        version: strategyVersion,
        mode: ExecutionMode.PAPER,
        allocatedCapital: toDecimal(allocation),
        credentialsId,
      });
      executionId = created.execution?.id ?? "";
      if (!executionId) throw new Error("No execution returned.");
      // Funds the sleeve (allocate_capital) and marks the execution running.
      await strategyClient.startExecution({ context, executionId });
    } catch (e) {
      set({
        deploying: false,
        error:
          e instanceof ConnectError
            ? e.message
            : "Could not deploy this strategy.",
      });
      return null;
    }

    let live = false;
    let liveError: string | null = null;
    let sessionId: string | null = null;
    if (goLive) {
      try {
        const started = await tradingClient.startSession({
          context,
          strategyId,
          strategyVersion,
          name: `${strategyName} (paper)`,
          mode: ExecutionMode.PAPER,
          credentialsId,
          symbols: [],
          executionId,
        });
        sessionId = started.session?.id || null;
        live = true;
      } catch (e) {
        liveError =
          e instanceof ConnectError
            ? e.message
            : "Could not start paper trading.";
      }
    }

    set({ deploying: false });
    // The sleeve consumed free cash either way, so refresh what's allocatable.
    useFundingStore
      .getState()
      .resolveAccount()
      .catch(() => undefined);
    return { executionId, sessionId, live, liveError };
  },

  clearError: () => set({ error: null }),
}));
