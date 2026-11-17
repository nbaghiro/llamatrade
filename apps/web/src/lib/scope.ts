/** Which money a page shows (mode2 A). Each page keeps its own choice, in its address. */

export type AccountScope = 'all' | 'live' | 'paper';

export const SCOPE_PARAM = 'scope';

export function parseScope(raw: string | null | undefined): AccountScope | null {
  return raw === 'all' || raw === 'live' || raw === 'paper' ? raw : null;
}

/** Whether something on a live or paper account belongs in the scope. */
export function inScope(scope: AccountScope, isLive: boolean): boolean {
  return scope === 'all' || (scope === 'live') === isLive;
}

/** "••4821": the last four characters of what we know of the key. */
export function maskedKey(keyPrefix: string): string {
  const tail = keyPrefix.trim().slice(-4);
  return tail ? `••${tail.toUpperCase()}` : '';
}

export interface ScopeAccount {
  isPaper: boolean;
  keyPrefix: string;
}

export interface ScopeChoice {
  key: AccountScope;
  label: string;
}

/**
 * The choices for the accounts connected: "All accounts" only when both kinds exist, then one
 * entry per kind, named by its first account. No accounts gives no choices.
 */
export function scopeChoices(accounts: readonly ScopeAccount[]): ScopeChoice[] {
  const live = accounts.find((a) => !a.isPaper);
  const paper = accounts.find((a) => a.isPaper);
  const named = (kind: string, a: ScopeAccount) => `${kind} ${maskedKey(a.keyPrefix)}`.trim();
  const out: ScopeChoice[] = [];
  if (live && paper) out.push({ key: 'all', label: 'All accounts' });
  if (live) out.push({ key: 'live', label: named('Live', live) });
  if (paper) out.push({ key: 'paper', label: named('Paper', paper) });
  return out;
}

/** The scope to show: the address wins, then what this page last used, then everything. */
export function resolveScope(
  fromUrl: AccountScope | null,
  remembered: AccountScope | null,
  available: readonly AccountScope[]
): AccountScope {
  for (const s of [fromUrl, remembered]) {
    if (s && (available.length === 0 || available.includes(s))) return s;
  }
  return available[0] ?? 'all';
}
