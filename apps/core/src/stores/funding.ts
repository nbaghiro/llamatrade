import { ConnectError } from "@connectrpc/connect";
import { create } from "zustand";

import type { AlpacaCredentialsListItem } from "@llamatrade/core/proto/auth_pb";
import { type Sleeve, SleeveType } from "@llamatrade/core/proto/ledger_pb";
import { authClient, ledgerClient } from "../net";
import { num } from "../format";

import { getTenantContext } from "../net";

/** number → proto Decimal (cents-precise string). */
function toDecimal(value: number): { value: string } {
  return { value: value.toFixed(2) };
}
/** proto Decimal → number. */
function toNumber(d?: { value: string }): number {
  return num(d);
}

/**
 * Allocatable cash in a sleeve: balance − reserved (free is derived, not stored).
 * Only the Unallocated sleeve's free cash can fund a new strategy — the portfolio
 * summary's "cash" also counts residual cash parked inside each strategy sleeve.
 */
export function freeCash(sleeve?: Sleeve): number {
  if (!sleeve?.cash) return 0;
  return toNumber(sleeve.cash.balance) - toNumber(sleeve.cash.reserved);
}

interface FundingState {
  /** Ledger account the money lives in (anchored to the paper credential). */
  accountId: string | null;
  /** The active paper credential funding + strategies allocate against. */
  paperCredentialId: string | null;
  credentials: AlpacaCredentialsListItem[];
  /** Unallocated sleeve's free cash — the only capital a new strategy can draw. */
  unallocatedCash: number;
  resolving: boolean;
  resolved: boolean;
  submitting: boolean;
  error: string | null;

  /** True once resolved and a paper account exists to fund. */
  hasAccount: () => boolean;
  /** List credentials → pick the active paper cred → get/create its ledger account. */
  resolveAccount: () => Promise<void>;
  /** Deposit paper capital into Unallocated; returns the new free-cash balance, or null on failure. */
  addFunds: (amount: number) => Promise<number | null>;
  clearError: () => void;
}

let inFlight: Promise<void> | null = null;

export const useFundingStore = create<FundingState>((set, get) => {
  const resolveOnce = async (): Promise<void> => {
    set({ resolving: true, error: null });
    try {
      const context = getTenantContext();
      // ListAlpacaCredentials derives the tenant from the JWT (no context arg).
      const credsRes = await authClient.listAlpacaCredentials({});
      const creds = credsRes.credentials;
      // The ledger account anchors to a paper credential; prefer an active one.
      const paper =
        creds.find((c) => c.isPaper && c.isActive) ??
        creds.find((c) => c.isActive) ??
        null;
      if (!paper) {
        set({
          credentials: creds,
          paperCredentialId: null,
          accountId: null,
          resolving: false,
          resolved: true,
        });
        return;
      }
      const acct = await ledgerClient.getOrCreateAccount({
        context,
        credentialsId: paper.id,
      });
      const unallocated = acct.baseSleeves.find(
        (s) => s.type === SleeveType.UNALLOCATED,
      );
      set({
        credentials: creds,
        paperCredentialId: paper.id,
        accountId: acct.account?.id ?? null,
        unallocatedCash: freeCash(unallocated),
        resolving: false,
        resolved: true,
      });
    } catch (e) {
      set({
        resolving: false,
        resolved: true,
        error:
          e instanceof ConnectError
            ? e.message
            : "Could not load your account.",
      });
    }
  };

  return {
    accountId: null,
    paperCredentialId: null,
    credentials: [],
    unallocatedCash: 0,
    resolving: false,
    resolved: false,
    submitting: false,
    error: null,

    hasAccount: () => get().accountId !== null,

    resolveAccount: () => {
      inFlight ??= resolveOnce().finally(() => {
        inFlight = null;
      });
      return inFlight;
    },

    addFunds: async (amount) => {
      if (!Number.isFinite(amount) || amount <= 0) {
        set({ error: "Enter an amount greater than $0." });
        return null;
      }
      let accountId = get().accountId;
      if (!accountId) {
        await get().resolveAccount();
        accountId = get().accountId;
      }
      if (!accountId) {
        set({
          error:
            "No paper account is connected yet. Connect your Alpaca paper keys in Settings first.",
        });
        return null;
      }
      set({ submitting: true, error: null });
      try {
        const context = getTenantContext();
        const res = await ledgerClient.depositFunds({
          context,
          accountId,
          amount: toDecimal(amount),
          // Idempotency key: a retried deposit must be a no-op, not a second credit.
          requestId: crypto.randomUUID(),
        });
        const free = freeCash(res.unallocated);
        set({ submitting: false, unallocatedCash: free });
        return free;
      } catch (e) {
        set({
          submitting: false,
          error:
            e instanceof ConnectError
              ? e.message
              : "The paper funds could not be added. Please try again.",
        });
        return null;
      }
    },

    clearError: () => set({ error: null }),
  };
});

export interface LiveAccount {
  credentialsId: string;
  /** The credential's name, e.g. "Live account". */
  name: string;
  /** Alpaca account number; empty when not yet known. */
  accountNumber: string;
  /** Free cash in the live account's Unallocated sleeve. */
  unallocatedCash: number;
}

/**
 * The active live Alpaca credential and the free cash its ledger account can fund a session
 * with; null when no live account is connected. Throws when the ledger can't be read.
 */
export async function readLiveAccount(): Promise<LiveAccount | null> {
  const creds = (await authClient.listAlpacaCredentials({})).credentials;
  const live = creds.find((c) => !c.isPaper && c.isActive);
  if (!live) return null;
  const acct = await ledgerClient.getOrCreateAccount({
    context: getTenantContext(),
    credentialsId: live.id,
  });
  const unallocated = acct.baseSleeves.find(
    (s) => s.type === SleeveType.UNALLOCATED,
  );
  return {
    credentialsId: live.id,
    name: live.name,
    accountNumber: live.accountNumber,
    unallocatedCash: freeCash(unallocated),
  };
}
