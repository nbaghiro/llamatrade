/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  listAlpacaCredentials,
  validateAlpacaCredentials,
  createAlpacaCredentials,
  deleteAlpacaCredentials,
} = vi.hoisted(() => ({
  listAlpacaCredentials: vi.fn(),
  validateAlpacaCredentials: vi.fn(),
  createAlpacaCredentials: vi.fn(),
  deleteAlpacaCredentials: vi.fn(),
}));

vi.mock('@llamatrade/core/net', () => ({
  authClient: {
    listAlpacaCredentials,
    validateAlpacaCredentials,
    createAlpacaCredentials,
    deleteAlpacaCredentials,
  },
}));

import { ConnectError } from '@connectrpc/connect';
import { useBrokerStore } from '@llamatrade/core/stores/broker';

const INPUT = { name: 'My keys', apiKey: 'AK', apiSecret: 'SK', isPaper: true };

beforeEach(() => {
  vi.clearAllMocks();
  useBrokerStore.setState({
    credentials: [],
    loaded: false,
    loading: false,
    connecting: false,
    checking: false,
    lastCheck: null,
    error: null,
  });
  listAlpacaCredentials.mockResolvedValue({ credentials: [{ id: 'c1' }] });
  validateAlpacaCredentials.mockResolvedValue({ valid: true });
  createAlpacaCredentials.mockResolvedValue({});
  deleteAlpacaCredentials.mockResolvedValue({});
});

describe('fetch', () => {
  it('loads the credential list', async () => {
    await useBrokerStore.getState().fetch();

    const state = useBrokerStore.getState();
    expect(state.credentials).toHaveLength(1);
    expect(state.loaded).toBe(true);
    expect(state.loading).toBe(false);
  });

  it('marks the load finished even when it fails', async () => {
    listAlpacaCredentials.mockRejectedValue(new ConnectError('nope'));

    await useBrokerStore.getState().fetch();

    const state = useBrokerStore.getState();
    expect(state.loaded).toBe(true);
    expect(state.loading).toBe(false);
    expect(state.error).toBeTruthy();
  });
});

describe('connect', () => {
  it('validates before storing, then refreshes the list', async () => {
    const ok = await useBrokerStore.getState().connect(INPUT);

    expect(ok).toBe(true);
    expect(validateAlpacaCredentials).toHaveBeenCalledWith({
      apiKey: 'AK',
      apiSecret: 'SK',
      isPaper: true,
    });
    expect(createAlpacaCredentials).toHaveBeenCalled();
    expect(listAlpacaCredentials).toHaveBeenCalled();
    expect(useBrokerStore.getState().connecting).toBe(false);
  });

  it('never stores keys Alpaca rejected', async () => {
    validateAlpacaCredentials.mockResolvedValue({ valid: false, message: 'bad key' });

    const ok = await useBrokerStore.getState().connect(INPUT);

    expect(ok).toBe(false);
    expect(createAlpacaCredentials).not.toHaveBeenCalled();
    expect(useBrokerStore.getState().error).toBe('bad key');
  });

  it('falls back to a generic message when the rejection carries none', async () => {
    validateAlpacaCredentials.mockResolvedValue({ valid: false });

    await useBrokerStore.getState().connect(INPUT);

    expect(useBrokerStore.getState().error).toMatch(/rejected by Alpaca/i);
  });

  it.each([
    ['   ', true, 'Paper account'],
    ['   ', false, 'Live account'],
  ])('names a blank-named credential by mode (%s, paper=%s)', async (name, isPaper, expected) => {
    await useBrokerStore.getState().connect({ ...INPUT, name, isPaper });

    expect(createAlpacaCredentials.mock.calls[0][0].name).toBe(expected);
  });

  it('trims a supplied name', async () => {
    await useBrokerStore.getState().connect({ ...INPUT, name: '  Trimmed  ' });

    expect(createAlpacaCredentials.mock.calls[0][0].name).toBe('Trimmed');
  });

  it('reports a thrown validation error and clears the busy flag', async () => {
    validateAlpacaCredentials.mockRejectedValue(new ConnectError('upstream down'));

    const ok = await useBrokerStore.getState().connect(INPUT);

    expect(ok).toBe(false);
    expect(useBrokerStore.getState().connecting).toBe(false);
    expect(useBrokerStore.getState().error).toContain('upstream down');
  });
});

describe('remove', () => {
  it('drops the credential locally after the server accepts', async () => {
    useBrokerStore.setState({ credentials: [{ id: 'c1' }, { id: 'c2' }] as never });

    const ok = await useBrokerStore.getState().remove('c1');

    expect(ok).toBe(true);
    expect(useBrokerStore.getState().credentials.map((c) => c.id)).toEqual(['c2']);
  });

  it('forgets the last check once the keys are gone', async () => {
    useBrokerStore.setState({
      credentials: [{ id: 'c1' }] as never,
      lastCheck: { at: new Date(), valid: true, isPaper: true, accountStatus: '', message: '' },
    });

    await useBrokerStore.getState().remove('c1');

    expect(useBrokerStore.getState().lastCheck).toBeNull();
  });

  it('keeps the credential listed when deletion is refused', async () => {
    useBrokerStore.setState({ credentials: [{ id: 'c1' }] as never });
    deleteAlpacaCredentials.mockRejectedValue(new ConnectError('in use by a running session'));

    const ok = await useBrokerStore.getState().remove('c1');

    expect(ok).toBe(false);
    // The guard exists server-side; the UI must not pretend the key is gone.
    expect(useBrokerStore.getState().credentials.map((c) => c.id)).toEqual(['c1']);
    expect(useBrokerStore.getState().error).toContain('in use');
  });
});

describe('check', () => {
  it('validates without storing and records when this browser asked', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-16T15:40:00Z'));
    validateAlpacaCredentials.mockResolvedValue({ valid: true, accountStatus: 'ACTIVE' });

    const result = await useBrokerStore
      .getState()
      .check({ apiKey: 'AK', apiSecret: 'SK', isPaper: true });

    expect(createAlpacaCredentials).not.toHaveBeenCalled();
    expect(validateAlpacaCredentials).toHaveBeenCalledWith({
      apiKey: 'AK',
      apiSecret: 'SK',
      isPaper: true,
    });
    expect(result).toEqual({
      at: new Date('2026-11-16T15:40:00Z'),
      valid: true,
      isPaper: true,
      accountStatus: 'ACTIVE',
      message: '',
    });
    expect(useBrokerStore.getState().lastCheck).toEqual(result);
    expect(useBrokerStore.getState().checking).toBe(false);
    vi.useRealTimers();
  });

  it("records a rejection with Alpaca's reason, or a plain one when none is given", async () => {
    validateAlpacaCredentials.mockResolvedValueOnce({
      valid: false,
      message: 'These look like live keys',
    });
    const first = await useBrokerStore
      .getState()
      .check({ apiKey: 'AK', apiSecret: 'SK', isPaper: true });
    expect(first?.valid).toBe(false);
    expect(first?.message).toBe('These look like live keys');

    validateAlpacaCredentials.mockResolvedValueOnce({ valid: false });
    const second = await useBrokerStore
      .getState()
      .check({ apiKey: 'AK', apiSecret: 'SK', isPaper: true });
    expect(second?.message).toMatch(/rejected by Alpaca/i);
  });

  it('keeps the previous result when Alpaca cannot be reached', async () => {
    const earlier = { at: new Date(0), valid: true, isPaper: true, accountStatus: '', message: '' };
    useBrokerStore.setState({ lastCheck: earlier });
    validateAlpacaCredentials.mockRejectedValue(new ConnectError('Could not reach Alpaca'));

    const result = await useBrokerStore
      .getState()
      .check({ apiKey: 'AK', apiSecret: 'SK', isPaper: true });

    expect(result).toBeNull();
    expect(useBrokerStore.getState().lastCheck).toBe(earlier);
    expect(useBrokerStore.getState().error).toContain('Could not reach Alpaca');
    expect(useBrokerStore.getState().checking).toBe(false);
  });
});
