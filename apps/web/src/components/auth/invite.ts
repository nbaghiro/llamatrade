const KEY = 'llamatrade-invite';

/** Keeps the invite code across the Alpaca sign-up round trip, in this tab only. */
export function rememberInvite(code: string): void {
  try {
    if (code.trim()) sessionStorage.setItem(KEY, code.trim());
  } catch {
    return;
  }
}

export function recalledInvite(): string {
  try {
    return sessionStorage.getItem(KEY) ?? '';
  } catch {
    return '';
  }
}

export function forgetInvite(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    return;
  }
}
