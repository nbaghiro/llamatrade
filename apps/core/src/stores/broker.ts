/**
 * Broker store — links the user's own Alpaca keys (ValidateAlpacaCredentials →
 * CreateAlpacaCredentials). Keys are validated with Alpaca, then stored encrypted
 * server-side; the raw secret never persists client-side. These RPCs derive the
 * tenant from the JWT, so they take no context arg. Shared by web + mobile.
 */
import { ConnectError } from "@connectrpc/connect";
import { create } from "zustand";

import type { AlpacaCredentialsListItem } from "@llamatrade/core/proto/auth_pb";

import { authClient } from "../net";

function errorMessage(e: unknown): string {
  if (e instanceof ConnectError) return e.rawMessage || e.message;
  return e instanceof Error ? e.message : "Something went wrong";
}

interface ConnectInput {
  name: string;
  apiKey: string;
  apiSecret: string;
  isPaper: boolean;
}

export interface CredentialCheck {
  /** When this browser made the call, not when the trading service last checked. */
  at: Date;
  valid: boolean;
  isPaper: boolean;
  accountStatus: string;
  message: string;
}

type CheckInput = Omit<ConnectInput, "name">;

interface BrokerState {
  credentials: AlpacaCredentialsListItem[];
  loaded: boolean;
  loading: boolean;
  connecting: boolean;
  checking: boolean;
  lastCheck: CredentialCheck | null;
  error: string | null;
  fetch: () => Promise<void>;
  /** Validate then persist. Returns true on success; sets `error` on rejection. */
  connect: (input: ConnectInput) => Promise<boolean>;
  /** Validate with Alpaca without storing anything, and record the result. */
  check: (input: CheckInput) => Promise<CredentialCheck | null>;
  /** Returns false when the server refuses, e.g. while a session still uses the keys. */
  remove: (id: string) => Promise<boolean>;
  clearError: () => void;
}

export const useBrokerStore = create<BrokerState>((set) => ({
  credentials: [],
  loaded: false,
  loading: false,
  connecting: false,
  checking: false,
  lastCheck: null,
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
      const check = await authClient.validateAlpacaCredentials({
        apiKey,
        apiSecret,
        isPaper,
      });
      if (!check.valid) {
        set({
          connecting: false,
          error: check.message || "Those credentials were rejected by Alpaca.",
        });
        return false;
      }
      await authClient.createAlpacaCredentials({
        name: name.trim() || `${isPaper ? "Paper" : "Live"} account`,
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

  check: async ({ apiKey, apiSecret, isPaper }) => {
    set({ checking: true, error: null });
    try {
      const res = await authClient.validateAlpacaCredentials({
        apiKey,
        apiSecret,
        isPaper,
      });
      const result: CredentialCheck = {
        at: new Date(),
        valid: res.valid,
        isPaper,
        accountStatus: res.accountStatus,
        message: res.valid
          ? ""
          : res.message || "Those credentials were rejected by Alpaca.",
      };
      set({ checking: false, lastCheck: result });
      return result;
    } catch (e) {
      set({ checking: false, error: errorMessage(e) });
      return null;
    }
  },

  remove: async (id) => {
    try {
      await authClient.deleteAlpacaCredentials({ credentialsId: id });
      set((s) => ({
        credentials: s.credentials.filter((c) => c.id !== id),
        lastCheck: null,
      }));
      return true;
    } catch (e) {
      set({ error: errorMessage(e) });
      return false;
    }
  },

  clearError: () => set({ error: null }),
}));
