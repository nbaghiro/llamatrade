import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { OfflineBannerView } from '../../components/states/OfflineBanner';
import { createOnlineTracker, staleSince, type OnlineEnv } from '../useOnline';

function fakeEnv(startOnline: boolean) {
  let online = startOnline;
  const handlers: Record<'online' | 'offline', Set<() => void>> = {
    online: new Set(),
    offline: new Set(),
  };
  const env: OnlineEnv = {
    isOnline: () => online,
    addEventListener: (type, l) => handlers[type].add(l),
    removeEventListener: (type, l) => handlers[type].delete(l),
  };
  const fire = (next: boolean) => {
    online = next;
    handlers[next ? 'online' : 'offline'].forEach((l) => l());
  };
  return { env, fire, handlers };
}

const T0 = new Date('2026-11-16T15:42:00Z');
const T1 = new Date('2026-11-16T15:50:00Z');

describe('online tracker', () => {
  it('starts from the browser state', () => {
    expect(createOnlineTracker(fakeEnv(true).env).getSnapshot()).toEqual({
      online: true,
      offlineSince: null,
    });
    expect(createOnlineTracker(fakeEnv(false).env, () => T0).getSnapshot()).toEqual({
      online: false,
      offlineSince: T0,
    });
  });

  it('goes offline with a timestamp and clears it on reconnect', () => {
    const { env, fire } = fakeEnv(true);
    let now = T0;
    const tracker = createOnlineTracker(env, () => now);
    const listener = vi.fn();
    tracker.subscribe(listener);

    fire(false);
    expect(tracker.getSnapshot()).toEqual({ online: false, offlineSince: T0 });
    expect(listener).toHaveBeenCalledTimes(1);

    now = T1;
    fire(false);
    expect(tracker.getSnapshot().offlineSince).toBe(T0);
    expect(listener).toHaveBeenCalledTimes(1);

    fire(true);
    expect(tracker.getSnapshot()).toEqual({ online: true, offlineSince: null });
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it('keeps one snapshot object per state, as useSyncExternalStore needs', () => {
    const { env, fire } = fakeEnv(true);
    const tracker = createOnlineTracker(env, () => T0);
    tracker.subscribe(() => undefined);
    const a = tracker.getSnapshot();
    expect(tracker.getSnapshot()).toBe(a);
    fire(false);
    const b = tracker.getSnapshot();
    expect(tracker.getSnapshot()).toBe(b);
    expect(b).not.toBe(a);
  });

  it('catches a change that happened before anyone subscribed', () => {
    const { env, fire } = fakeEnv(true);
    const tracker = createOnlineTracker(env, () => T0);
    fire(false);
    tracker.subscribe(() => undefined);
    expect(tracker.getSnapshot().online).toBe(false);
  });

  it('listens only while subscribed', () => {
    const { env, handlers } = fakeEnv(true);
    const tracker = createOnlineTracker(env);
    const stopA = tracker.subscribe(() => undefined);
    const stopB = tracker.subscribe(() => undefined);
    expect(handlers.online.size).toBe(1);
    stopA();
    expect(handlers.offline.size).toBe(1);
    stopB();
    expect(handlers.online.size).toBe(0);
    expect(handlers.offline.size).toBe(0);
  });

  it('marks itself online when a retry probe answers, and stays offline when it fails', async () => {
    const { env } = fakeEnv(false);
    const tracker = createOnlineTracker(env, () => T0);
    tracker.subscribe(() => undefined);

    expect(await tracker.retry(() => Promise.reject(new Error('no network')))).toBe(false);
    expect(tracker.getSnapshot().online).toBe(false);

    expect(await tracker.retry(() => Promise.resolve(true))).toBe(true);
    expect(tracker.getSnapshot().online).toBe(true);
  });
});

describe('offline banner', () => {
  it('says when the figures are from, in New York time', () => {
    expect(staleSince(T0, T1)).toBe('Figures are from 10:42 ET.');
    expect(staleSince(T0, new Date('2026-11-17T15:00:00Z'))).toBe('Figures are from Mon 10:42 ET.');
  });

  it('says what keeps working and offers a retry', () => {
    const html = renderToStaticMarkup(
      <OfflineBannerView
        offlineSince={T0}
        now={T1}
        retrying={false}
        stillOffline={false}
        onRetry={() => undefined}
      />
    );
    expect(html).toContain('You&#x27;re offline.');
    expect(html).toContain('The figures here are from 10:42 ET.');
    expect(html).toContain('keep trading');
    expect(html).toContain('Trying again every 10 seconds');
    expect(html).toContain('Try now');
    expect(html).toContain('role="status"');
    expect(html).not.toContain('text-risk');
  });

  it('shows progress while retrying and says when the retry failed', () => {
    const html = renderToStaticMarkup(
      <OfflineBannerView
        offlineSince={T0}
        now={T1}
        retrying
        stillOffline
        onRetry={() => undefined}
      />
    );
    expect(html).toContain('Checking…');
    expect(html).toContain('Still no connection.');
  });
});
