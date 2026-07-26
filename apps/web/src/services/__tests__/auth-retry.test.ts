import { Code, ConnectError } from '@connectrpc/connect';
import { authRetryInterceptor } from '@llamatrade/core/net';
import { describe, expect, it, vi } from 'vitest';


const req = (name: string) => ({ method: { name }, header: new Headers() });

describe('authRetryInterceptor', () => {
  it('refreshes and retries once on Unauthenticated', async () => {
    let calls = 0;
    const next = vi.fn(async () => {
      calls += 1;
      if (calls === 1) throw new ConnectError('unauth', Code.Unauthenticated);
      return { ok: true };
    });
    const refreshTokens = vi.fn(async () => true);

    const invoke = authRetryInterceptor({ refreshTokens })(next as never);
    const res = await invoke(req('GetPortfolio') as never);

    expect(res).toEqual({ ok: true });
    expect(next).toHaveBeenCalledTimes(2);
    expect(refreshTokens).toHaveBeenCalledTimes(1);
  });

  it('drops the session when refresh fails', async () => {
    const next = vi.fn(async () => {
      throw new ConnectError('unauth', Code.Unauthenticated);
    });
    const onUnauthenticated = vi.fn();

    const invoke = authRetryInterceptor({
      refreshTokens: async () => false,
      onUnauthenticated,
    })(next as never);

    await expect(invoke(req('GetPortfolio') as never)).rejects.toBeInstanceOf(ConnectError);
    expect(onUnauthenticated).toHaveBeenCalledTimes(1);
  });

  it('shares one in-flight refresh across concurrent 401s', async () => {
    let calls = 0;
    const next = vi.fn(async () => {
      calls += 1;
      if (calls <= 2) throw new ConnectError('unauth', Code.Unauthenticated);
      return { ok: true };
    });
    const refreshTokens = vi.fn(async () => true);

    const invoke = authRetryInterceptor({ refreshTokens })(next as never);
    await Promise.all([invoke(req('A') as never), invoke(req('B') as never)]);

    expect(refreshTokens).toHaveBeenCalledTimes(1);
  });

  it('does not refresh or retry public methods', async () => {
    const next = vi.fn(async () => {
      throw new ConnectError('unauth', Code.Unauthenticated);
    });
    const refreshTokens = vi.fn(async () => true);

    const invoke = authRetryInterceptor({ refreshTokens })(next as never);

    await expect(invoke(req('Login') as never)).rejects.toBeInstanceOf(ConnectError);
    expect(refreshTokens).not.toHaveBeenCalled();
  });
});
