import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface User {
  id: string;
  email: string;
  roles: string[];
  tenantId: string;
  firstName?: string;
  lastName?: string;
  avatarUrl?: string;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  login: (user: User, accessToken: string, refreshToken: string) => void;
  logout: () => void;
  setTokens: (accessToken: string, refreshToken: string) => void;
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

/**
 * Get tenant context for API requests.
 * Returns undefined if not authenticated.
 */
export function getTenantContext(): { tenantId: string; userId: string } | undefined {
  const { user } = useAuthStore.getState();
  if (!user || !user.tenantId) return undefined;
  return {
    tenantId: user.tenantId,
    userId: user.id,
  };
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,

      login: (user, accessToken, refreshToken) =>
        set({
          user,
          accessToken,
          refreshToken,
          isAuthenticated: true,
        }),

      logout: () =>
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
        }),

      setTokens: (accessToken, refreshToken) =>
        set({ accessToken, refreshToken }),
    }),
    {
      name: 'llamatrade-auth',
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
