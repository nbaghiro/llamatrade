/**
 * Shared auth store factory.
 *
 * Web and mobile hold identical auth state (user + tokens + tenant identity);
 * the only platform difference is the persistence backend, which each app injects
 * (`localStorage` on web, the secure enclave on mobile). `hasHydrated` matters
 * only for async stores (mobile) but is harmless on web — it flips true right
 * after rehydration either way, so screens can gate routing on it uniformly.
 */
import { create, type StoreApi, type UseBoundStore } from 'zustand';
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware';

export interface AuthUser {
  id: string;
  email: string;
  roles: string[];
  tenantId: string;
  firstName?: string;
  lastName?: string;
  avatarUrl?: string;
}

export interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  /** Async storage (mobile) is not ready on first paint — gate routing on this. */
  hasHydrated: boolean;
  setHydrated: () => void;
  setSession: (user: AuthUser, accessToken: string, refreshToken: string) => void;
  /** Replace just the tokens after a refresh, keeping the current user. */
  updateTokens: (accessToken: string, refreshToken: string) => void;
  logout: () => void;
}

/** TenantContext-shaped identity threaded into every RPC. */
export interface TenantContext {
  tenantId: string;
  userId: string;
  roles: string[];
}

/** True when the JWT is missing, malformed, or past its `exp`. */
export function isTokenExpired(token: string | null | undefined): boolean {
  if (!token) return true;
  try {
    const { exp } = JSON.parse(atob(token.split('.')[1])) as { exp?: number };
    return typeof exp !== 'number' || exp * 1000 <= Date.now();
  } catch {
    return true;
  }
}

export interface AuthStore {
  useAuthStore: UseBoundStore<StoreApi<AuthState>>;
  /** Reads the current identity for RPC threading; undefined when signed out. */
  getTenantContext: () => TenantContext | undefined;
}

/**
 * Build an auth store bound to a platform storage backend. Pass `storage` to
 * persist elsewhere than the default (`localStorage`); mobile passes its secure
 * enclave adapter.
 */
export function createAuthStore(options?: { storage?: StateStorage }): AuthStore {
  const useAuthStore = create<AuthState>()(
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
        ...(options?.storage ? { storage: createJSONStorage(() => options.storage!) } : {}),
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

  const getTenantContext = (): TenantContext | undefined => {
    const u = useAuthStore.getState().user;
    return u ? { tenantId: u.tenantId, userId: u.id, roles: u.roles ?? [] } : undefined;
  };

  return { useAuthStore, getTenantContext };
}
