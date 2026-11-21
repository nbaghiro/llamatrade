import { readLiveAccount, type LiveAccount } from '@llamatrade/core/stores/funding';
import { useEffect, useState } from 'react';

export type LiveAccountState =
  | { kind: 'loading' }
  | { kind: 'none' }
  | { kind: 'ready'; account: LiveAccount }
  | { kind: 'error' };

/** The connected live Alpaca account and its free cash, read once per mount. */
export function useLiveAccount(): LiveAccountState {
  const [state, setState] = useState<LiveAccountState>({ kind: 'loading' });
  useEffect(() => {
    let live = true;
    readLiveAccount()
      .then((account) => {
        if (live) setState(account ? { kind: 'ready', account } : { kind: 'none' });
      })
      .catch(() => {
        if (live) setState({ kind: 'error' });
      });
    return () => {
      live = false;
    };
  }, []);
  return state;
}

/** Free cash in the live account, or null when there is no live account or it couldn't be read. */
export function liveFreeCash(state: LiveAccountState): number | null {
  return state.kind === 'ready' ? state.account.unallocatedCash : null;
}
