import { ExecutionMode } from '@llamatrade/core/proto/common_pb';

import { maskedKey } from '../../lib/scope';

export interface ConnectionInput {
  id: string;
  name: string;
  apiKeyPrefix: string;
  isPaper: boolean;
  isActive: boolean;
}

export interface SessionInput {
  mode: ExecutionMode;
  isActive: boolean;
  /** The sleeve's value now; null when the portfolio service has no figure. */
  equity: number | null;
}

export interface ConnectionRow {
  id: string;
  mode: 'live' | 'paper';
  masked: string;
  name: string;
  connected: boolean;
  /** Running sessions in this account's mode. */
  sessions: number;
  /** Their combined value; null when none has a figure. */
  value: number | null;
}

/** One row per connected Alpaca account, live first, with what runs on it (account2 A). */
export function connectionRows(
  credentials: readonly ConnectionInput[],
  sessions: readonly SessionInput[]
): ConnectionRow[] {
  const rows = credentials.map((c) => {
    const mode: ExecutionMode = c.isPaper ? ExecutionMode.PAPER : ExecutionMode.LIVE;
    const running = sessions.filter((s) => s.isActive && s.mode === mode);
    const known = running.filter((s) => s.equity !== null);
    const value = known.reduce((sum, s) => sum + (s.equity ?? 0), 0);
    return {
      id: c.id,
      mode: c.isPaper ? ('paper' as const) : ('live' as const),
      masked: maskedKey(c.apiKeyPrefix),
      name: c.name,
      connected: c.isActive,
      sessions: running.length,
      value: known.length ? value : null,
    };
  });
  return rows.sort((a, b) => Number(a.mode === 'paper') - Number(b.mode === 'paper'));
}
