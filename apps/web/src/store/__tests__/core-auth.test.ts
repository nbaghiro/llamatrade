/**
 * The shared auth store factory: token-expiry checks and the identity threaded
 * into every RPC. Web and mobile both build on this, so a fault here is a
 * two-platform fault.
 */
import { createAuthStore, isTokenExpired } from '@llamatrade/core/stores/auth';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/** A JWT with only the fields the store reads (signature is never verified here). */
function jwt(payload: Record<string, unknown>): string {
  return `header.${btoa(JSON.stringify(payload))}.signature`;
}

const USER = {
  id: 'u1',
  email: 'a@b.c',
  roles: ['owner'],
  tenantId: 't1',
};

describe('isTokenExpired', () => {
  it('treats a missing token as expired', () => {
    expect(isTokenExpired(null)).toBe(true);
    expect(isTokenExpired(undefined)).toBe(true);
    expect(isTokenExpired('')).toBe(true);
  });

  it('treats a malformed token as expired rather than throwing', () => {
    expect(isTokenExpired('not-a-jwt')).toBe(true);
    expect(isTokenExpired('a.b.c')).toBe(true);
    expect(isTokenExpired(jwt({}))).toBe(true);
  });

  it('treats a non-numeric exp as expired', () => {
    expect(isTokenExpired(jwt({ exp: 'soon' }))).toBe(true);
  });

  it('is false for a token that has time left', () => {
    expect(isTokenExpired(jwt({ exp: Math.floor(Date.now() / 1000) + 600 }))).toBe(false);
  });

  it('is true once exp has passed', () => {
    expect(isTokenExpired(jwt({ exp: Math.floor(Date.now() / 1000) - 1 }))).toBe(true);
  });

  it('treats the exact expiry instant as expired', () => {
    const now = 1_800_000_000_000;
    vi.spyOn(Date, 'now').mockReturnValue(now);
    try {
      expect(isTokenExpired(jwt({ exp: now / 1000 }))).toBe(true);
    } finally {
      vi.restoreAllMocks();
    }
  });
});

describe('createAuthStore', () => {
  let store: ReturnType<typeof createAuthStore>;

  /** In-memory backend: the node test env has no localStorage. */
  function memoryStorage() {
    const cell = new Map<string, string>();
    return {
      getItem: (k: string) => cell.get(k) ?? null,
      setItem: (k: string, v: string) => void cell.set(k, v),
      removeItem: (k: string) => void cell.delete(k),
    };
  }

  beforeEach(() => {
    store = createAuthStore({ storage: memoryStorage() });
    store.useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    });
  });

  it('starts signed out with no tenant context', () => {
    expect(store.useAuthStore.getState().isAuthenticated).toBe(false);
    expect(store.getTenantContext()).toBeUndefined();
  });

  it('setSession authenticates and exposes the RPC identity', () => {
    store.useAuthStore.getState().setSession(USER, 'access', 'refresh');

    const state = store.useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.accessToken).toBe('access');
    expect(store.getTenantContext()).toEqual({
      tenantId: 't1',
      userId: 'u1',
      roles: ['owner'],
    });
  });

  it('defaults roles to an empty list when the user carries none', () => {
    store.useAuthStore
      .getState()
      .setSession({ ...USER, roles: undefined as unknown as string[] }, 'a', 'r');

    expect(store.getTenantContext()?.roles).toEqual([]);
  });

  it('updateTokens rotates the pair without dropping the user', () => {
    store.useAuthStore.getState().setSession(USER, 'old-access', 'old-refresh');

    store.useAuthStore.getState().updateTokens('new-access', 'new-refresh');

    const state = store.useAuthStore.getState();
    expect(state.accessToken).toBe('new-access');
    expect(state.refreshToken).toBe('new-refresh');
    expect(state.user?.id).toBe('u1');
    expect(state.isAuthenticated).toBe(true);
  });

  it('logout clears the session and the RPC identity', () => {
    store.useAuthStore.getState().setSession(USER, 'access', 'refresh');

    store.useAuthStore.getState().logout();

    const state = store.useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.accessToken).toBeNull();
    expect(state.refreshToken).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(store.getTenantContext()).toBeUndefined();
  });

  it('opens the routing gate once rehydration has run', () => {
    // Synchronous storage rehydrates during construction, so the gate is already
    // open here; on mobile's async enclave it opens later, hence the flag.
    expect(store.useAuthStore.getState().hasHydrated).toBe(true);

    store.useAuthStore.getState().setHydrated();

    expect(store.useAuthStore.getState().hasHydrated).toBe(true);
  });

  it('keeps the gate shut until an async backend finishes rehydrating', async () => {
    const pending = createAuthStore({
      storage: {
        getItem: () => new Promise<string | null>(() => {}), // never resolves
        setItem: () => {},
        removeItem: () => {},
      },
    });

    await Promise.resolve();

    expect(pending.useAuthStore.getState().hasHydrated).toBe(false);
  });

  it('persists through the injected storage backend', async () => {
    const written = new Map<string, string>();
    const scoped = createAuthStore({
      storage: {
        getItem: (k) => written.get(k) ?? null,
        setItem: (k, v) => void written.set(k, v),
        removeItem: (k) => void written.delete(k),
      },
    });

    scoped.useAuthStore.getState().setSession(USER, 'access', 'refresh');
    await Promise.resolve();

    const persisted = JSON.parse(written.get('llamatrade-auth') ?? '{}');
    expect(persisted.state.user.id).toBe('u1');
    expect(persisted.state.accessToken).toBe('access');
    // hasHydrated is derived per-process, never persisted.
    expect(persisted.state.hasHydrated).toBeUndefined();
  });
});
