import { ConnectError } from '@connectrpc/connect';
import { create } from 'zustand';

import type { AlpacaCredentialsListItem } from '../generated/proto/auth_pb';
import { type Sleeve, SleeveType } from '../generated/proto/ledger_pb';
import { authClient, ledgerClient } from '../services/grpc-client';

import { getTenantContext } from './auth';

/** number → proto Decimal (cents-precise string). */
function toDecimal(value: number): { value: string } {
  return { value: value.toFixed(2) };
}
/** proto Decimal → number. */
function toNumber(d?: { value: string }): number {
  return d?.value ? parseFloat(d.value) : 0;
}

/**
 * Allocatable cash in a sleeve: balance − reserved (free is derived, not stored).
 * Only the Unallocated sleeve's free cash can fund a new strategy — the portfolio
 * summary's "cash" also counts residual cash parked inside each strategy sleeve.
 */
function freeOf(sleeve?: Sleeve): number {
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

export const useFundingStore = create<FundingState>((set, get) => ({
  accountId: null,
  paperCredentialId: null,
  credentials: [],
  unallocatedCash: 0,
  resolving: false,
  resolved: false,
  submitting: false,
  error: null,

  hasAccount: () => get().accountId !== null,

  resolveAccount: async () => {
    if (get().resolving) return;
    set({ resolving: true, error: null });
    try {
      const context = getTenantContext();
      // ListAlpacaCredentials derives the tenant from the JWT (no context arg).
      const credsRes = await authClient.listAlpacaCredentials({});
      const creds = credsRes.credentials;
      // The ledger account anchors to a paper credential; prefer an active one.
      const paper =
        creds.find((c) => c.isPaper && c.isActive) ?? creds.find((c) => c.isActive) ?? null;
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
      const acct = await ledgerClient.getOrCreateAccount({ context, credentialsId: paper.id });
      const unallocated = acct.baseSleeves.find((s) => s.type === SleeveType.UNALLOCATED);
      set({
        credentials: creds,
        paperCredentialId: paper.id,
        accountId: acct.account?.id ?? null,
        unallocatedCash: freeOf(unallocated),
        resolving: false,
        resolved: true,
      });
    } catch (e) {
      set({
        resolving: false,
        resolved: true,
        error: e instanceof ConnectError ? e.message : 'Could not load your account.',
      });
    }
  },

  addFunds: async (amount) => {
    if (!Number.isFinite(amount) || amount <= 0) {
      set({ error: 'Enter an amount greater than $0.' });
      return null;
    }
    let accountId = get().accountId;
    if (!accountId) {
      await get().resolveAccount();
      accountId = get().accountId;
    }
    if (!accountId) {
      set({ error: 'No paper account is connected yet — connect Alpaca paper keys first.' });
      return null;
    }
    set({ submitting: true, error: null });
    try {
      const context = getTenantContext();
      const res = await ledgerClient.depositFunds({
        context,
        accountId,
        amount: toDecimal(amount),
      });
      const free = freeOf(res.unallocated);
      set({ submitting: false, unallocatedCash: free });
      return free;
    } catch (e) {
      set({
        submitting: false,
        error: e instanceof ConnectError ? e.message : 'Deposit failed — please try again.',
      });
      return null;
    }
  },

  clearError: () => set({ error: null }),
}));
