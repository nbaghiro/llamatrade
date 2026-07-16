/**
 * Auth store — the mobile analogue of apps/web/src/store/auth.ts.
 * Same shape (user + tokens + tenant), persisted to the secure enclave.
 * The transport factory reads `accessToken`; `tenantContext()` threads identity
 * into every RPC.
 */
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { secureStorage } from '../net/secure-storage';

export interface AuthUser {
  id: string;
  email: string;
  firstName?: string;
  lastName?: string;
  avatarUrl?: string;
  tenantId: string;
  roles: string[];
}

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  /** SecureStore is async — screens must wait for rehydration before routing. */
  hasHydrated: boolean;
  setHydrated: () => void;
  setSession: (user: AuthUser, accessToken: string, refreshToken: string) => void;
  /** Replace just the tokens after a refresh, keeping the current user. */
  updateTokens: (accessToken: string, refreshToken: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      hasHydrated: false,
      setHydrated: () => set({ hasHydrated: true }),
      setSession: (user, accessToken, refreshToken) =>
        set({ user, accessToken, refreshToken, isAuthenticated: true }),
      updateTokens: (accessToken, refreshToken) => set({ accessToken, refreshToken }),
      logout: () =>
        set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false }),
    }),
    {
      name: 'llamatrade-auth',
      storage: createJSONStorage(() => secureStorage),
      partialize: (s) => ({
        user: s.user,
        accessToken: s.accessToken,
        refreshToken: s.refreshToken,
        isAuthenticated: s.isAuthenticated,
      }),
      onRehydrateStorage: () => (state) => state?.setHydrated(),
    },
  ),
);

/** True when the JWT is missing, malformed, or past its `exp`. Mirrors the web. */
export function isTokenExpired(token: string | null | undefined): boolean {
  if (!token) return true;
  try {
    const { exp } = JSON.parse(atob(token.split('.')[1])) as { exp?: number };
    return typeof exp !== 'number' || exp * 1000 <= Date.now();
  } catch {
    return true;
  }
}

/** Build the TenantContext-shaped identity threaded into every RPC. */
export function tenantContext(): { tenantId: string; userId: string; roles: string[] } | undefined {
  const u = useAuthStore.getState().user;
  return u ? { tenantId: u.tenantId, userId: u.id, roles: u.roles ?? [] } : undefined;
}
