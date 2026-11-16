import { useSyncExternalStore } from 'react';

import { describeOpen } from '../lib/marketClock';

export interface OnlineSnapshot {
  online: boolean;
  /** When the connection dropped; the figures on screen are from then. Null while online. */
  offlineSince: Date | null;
}

export interface OnlineEnv {
  isOnline: () => boolean;
  addEventListener: (type: 'online' | 'offline', listener: () => void) => void;
  removeEventListener: (type: 'online' | 'offline', listener: () => void) => void;
}

export interface OnlineTracker {
  subscribe: (listener: () => void) => () => void;
  getSnapshot: () => OnlineSnapshot;
  /** Probes the network and marks the tracker online when the probe answers. */
  retry: (probe: () => Promise<boolean>) => Promise<boolean>;
}

const ONLINE: OnlineSnapshot = { online: true, offlineSince: null };

/** Follows the browser's online and offline events, keeping one stable snapshot per state. */
export function createOnlineTracker(
  env: OnlineEnv,
  now: () => Date = () => new Date()
): OnlineTracker {
  let snapshot: OnlineSnapshot = env.isOnline() ? ONLINE : { online: false, offlineSince: now() };
  const listeners = new Set<() => void>();

  const set = (online: boolean) => {
    if (online === snapshot.online) return;
    snapshot = online ? ONLINE : { online: false, offlineSince: now() };
    listeners.forEach((l) => l());
  };
  const onOnline = () => set(true);
  const onOffline = () => set(false);

  return {
    subscribe(listener) {
      if (listeners.size === 0) {
        env.addEventListener('online', onOnline);
        env.addEventListener('offline', onOffline);
        set(env.isOnline());
      }
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0) {
          env.removeEventListener('online', onOnline);
          env.removeEventListener('offline', onOffline);
        }
      };
    },
    getSnapshot: () => snapshot,
    async retry(probe) {
      const ok = await probe().catch(() => false);
      if (ok) set(true);
      return ok;
    },
  };
}

const browserTracker: OnlineTracker | null =
  typeof window === 'undefined'
    ? null
    : createOnlineTracker({
        isOnline: () => navigator.onLine,
        addEventListener: (type, l) => window.addEventListener(type, l),
        removeEventListener: (type, l) => window.removeEventListener(type, l),
      });

const noop = () => () => undefined;
const serverSnapshot = () => ONLINE;

/** A small same-origin request; any answer at all means the network is back. */
export async function probeNetwork(): Promise<boolean> {
  try {
    await fetch(`/favicon.svg?online=${Date.now()}`, { method: 'HEAD', cache: 'no-store' });
    return true;
  } catch {
    return false;
  }
}

export function retryConnection(): Promise<boolean> {
  return browserTracker ? browserTracker.retry(probeNetwork) : Promise.resolve(true);
}

/** Whether the browser is online, and since when it has been offline. */
export function useOnline(): OnlineSnapshot {
  return useSyncExternalStore(
    browserTracker?.subscribe ?? noop,
    browserTracker?.getSnapshot ?? serverSnapshot,
    serverSnapshot
  );
}

/** "Figures are from 10:42 ET", or with a weekday when the drop was on another day. */
export function staleSince(offlineSince: Date, now: Date): string {
  return `Figures are from ${describeOpen(offlineSince, now)}.`;
}
