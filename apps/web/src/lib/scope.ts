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

/** "••4821": the last four characters of the Alpaca account number, or empty when unknown. */
export function maskedAccount(accountNumber: string | undefined): string {
  const tail = (accountNumber ?? '').trim().slice(-4);
  return tail ? `••${tail.toUpperCase()}` : '';
}

/** Masked account numbers for a set of accounts, blank where two would show the same tail. */
export function distinctMasks(accountNumbers: readonly (string | undefined)[]): string[] {
  const masks = accountNumbers.map(maskedAccount);
  return masks.map((m) => (m && masks.filter((x) => x === m).length > 1 ? '' : m));
}

/**
 * "Alpaca live ••4821". The tail is left out when the account number is unknown or the other
 * account would show the same one.
 */
export function alpacaAccountLabel(
  live: boolean,
  accountNumber: string | undefined,
  otherAccountNumber?: string
): string {
  const [mask] = distinctMasks([accountNumber, otherAccountNumber]);
  return `Alpaca ${live ? 'live' : 'paper'}${mask ? ` ${mask}` : ''}`;
}

export interface ScopeAccount {
  isPaper: boolean;
  accountNumber: string;
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
  const shown = [live, paper].filter((a): a is ScopeAccount => a !== undefined);
  const masks = distinctMasks(shown.map((a) => a.accountNumber));
  const named = (kind: string, a: ScopeAccount) => `${kind} ${masks[shown.indexOf(a)]}`.trim();
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
