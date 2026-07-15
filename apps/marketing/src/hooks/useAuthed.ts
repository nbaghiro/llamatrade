import { useEffect, useState } from 'react';

/**
 * Storage key of the web app's persisted auth store (Zustand `persist`).
 * MUST stay in sync with the `name` in apps/web/src/store/auth.ts — the
 * marketing site and the SPA share a single origin (see the Caddyfile), so this
 * standalone marketing build reads the app's auth state straight from
 * localStorage. This is LlamaTrade's equivalent of how Galleo's marketing build
 * detects a session (it asks the API because its cookie is httpOnly); here the
 * JWT store is client-readable, so a synchronous read is enough — and it mirrors
 * how the app itself gates access (ProtectedRoute trusts `isAuthenticated`).
 */
const AUTH_STORAGE_KEY = 'llamatrade-auth';

interface PersistedAuth {
  state?: { isAuthenticated?: boolean; accessToken?: string | null };
}

function readAuthed(): boolean {
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return false;
    const parsed = JSON.parse(raw) as PersistedAuth;
    return Boolean(parsed.state?.isAuthenticated && parsed.state?.accessToken);
  } catch {
    // Storage blocked (private mode) or malformed JSON → treat as logged out.
    return false;
  }
}

/**
 * Whether a signed-in web-app session exists, read from the shared localStorage
 * auth store. Used to make marketing CTAs auth-aware ("Open App" vs sign-up).
 * Re-reads on cross-tab `storage` events so logging in/out in the app updates
 * the CTA here without a reload. Initialised synchronously (lazy `useState`) so
 * there is no flash of the signed-out CTA for an already-authenticated visitor.
 */
export function useAuthed(): boolean {
  const [authed, setAuthed] = useState<boolean>(readAuthed);

  useEffect(() => {
    const sync = (event: StorageEvent) => {
      // key === null fires on Storage.clear() (e.g. logout wipes everything).
      if (event.key === AUTH_STORAGE_KEY || event.key === null) setAuthed(readAuthed());
    };
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);

  return authed;
}
