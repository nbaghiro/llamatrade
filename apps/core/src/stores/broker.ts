/**
 * Broker store — links the user's own Alpaca keys (ValidateAlpacaCredentials →
 * CreateAlpacaCredentials). Keys are validated with Alpaca, then stored encrypted
 * server-side; the raw secret never persists client-side. These RPCs derive the
 * tenant from the JWT, so they take no context arg. Shared by web + mobile.
 */
import { ConnectError } from '@connectrpc/connect';
import { create } from 'zustand';

import type { AlpacaCredentialsListItem } from '@llamatrade/core/proto/auth_pb';

import { authClient } from '../net';

function errorMessage(e: unknown): string {
  if (e instanceof ConnectError) return e.rawMessage || e.message;
  return e instanceof Error ? e.message : 'Something went wrong';
}

interface ConnectInput {
  name: string;
  apiKey: string;
  apiSecret: string;
  isPaper: boolean;
}

interface BrokerState {
  credentials: AlpacaCredentialsListItem[];
  loaded: boolean;
  loading: boolean;
  connecting: boolean;
  error: string | null;
  fetch: () => Promise<void>;
  /** Validate then persist. Returns true on success; sets `error` on rejection. */
  connect: (input: ConnectInput) => Promise<boolean>;
  remove: (id: string) => Promise<void>;
  clearError: () => void;
}

export const useBrokerStore = create<BrokerState>((set) => ({
  credentials: [],
  loaded: false,
  loading: false,
  connecting: false,
  error: null,

  fetch: async () => {
    set({ loading: true });
    try {
      const res = await authClient.listAlpacaCredentials({});
      set({ credentials: res.credentials, loaded: true, loading: false });
    } catch (e) {
      set({ error: errorMessage(e), loading: false, loaded: true });
    }
  },

  connect: async ({ name, apiKey, apiSecret, isPaper }) => {
    set({ connecting: true, error: null });
    try {
      const check = await authClient.validateAlpacaCredentials({ apiKey, apiSecret, isPaper });
      if (!check.valid) {
        set({ connecting: false, error: check.message || 'Those credentials were rejected by Alpaca.' });
        return false;
      }
      await authClient.createAlpacaCredentials({
        name: name.trim() || `${isPaper ? 'Paper' : 'Live'} account`,
        apiKey,
        apiSecret,
        isPaper,
      });
      const res = await authClient.listAlpacaCredentials({});
      set({ credentials: res.credentials, connecting: false, loaded: true });
      return true;
    } catch (e) {
      set({ connecting: false, error: errorMessage(e) });
      return false;
    }
  },

  remove: async (id) => {
    try {
      await authClient.deleteAlpacaCredentials({ credentialsId: id });
      set((s) => ({ credentials: s.credentials.filter((c) => c.id !== id) }));
    } catch (e) {
      set({ error: errorMessage(e) });
    }
  },

  clearError: () => set({ error: null }),
}));
