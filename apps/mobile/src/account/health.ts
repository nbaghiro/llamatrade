/** Account health for the Account tab and the broker page. Mirrors apps/web/src/pages/settings/health.ts. */

export type AccountKind = 'live' | 'paper';

export interface HealthCredential {
  isPaper: boolean;
  isActive: boolean;
  apiKeyPrefix: string;
}

/** A key check run from this phone; the API keeps no check history of its own. */
export interface HealthCheck {
  at: Date;
  valid: boolean;
  isPaper: boolean;
  message: string;
}

export interface HealthSession {
  name: string;
  kind: AccountKind;
  running: boolean;
  /** The next scheduled rebalance day; the API has no time of day for it. */
  nextRun: Date | null;
}

export interface AccountProblem {
  kind: AccountKind;
  /** inactive: the stored keys are switched off; rejected: Alpaca refused them in a check. */
  reason: 'inactive' | 'rejected';
  at: Date | null;
  detail: string;
  /** Running sessions on this account, which can't place orders until it's fixed. */
  affected: string[];
  next: { name: string; at: Date } | null;
}

export interface AccountHealth {
  connected: AccountKind[];
  problems: AccountProblem[];
}

const kindOf = (isPaper: boolean): AccountKind => (isPaper ? 'paper' : 'live');

/** What's wrong with each connected Alpaca account and which sessions it holds up (broker2 A). */
export function accountHealth(
  credentials: readonly HealthCredential[],
  check: HealthCheck | null,
  sessions: readonly HealthSession[]
): AccountHealth {
  const connected: AccountKind[] = [];
  const problems: AccountProblem[] = [];
  for (const kind of ['live', 'paper'] as const) {
    const creds = credentials.filter((c) => kindOf(c.isPaper) === kind);
    if (creds.length === 0) continue;
    connected.push(kind);
    const active = creds.some((c) => c.isActive);
    const rejected = check !== null && !check.valid && kindOf(check.isPaper) === kind;
    if (active && !rejected) continue;
    const running = sessions.filter((s) => s.kind === kind && s.running);
    const upcoming = running
      .filter((s): s is HealthSession & { nextRun: Date } => s.nextRun !== null)
      .sort((a, b) => a.nextRun.getTime() - b.nextRun.getTime())[0];
    problems.push({
      kind,
      reason: rejected ? 'rejected' : 'inactive',
      at: rejected && check ? check.at : null,
      detail: rejected && check ? check.message : '',
      affected: running.map((s) => s.name),
      next: upcoming ? { name: upcoming.name, at: upcoming.nextRun } : null,
    });
  }
  return { connected, problems };
}

/** "10:38 ET". */
export function etTime(d: Date): string {
  return `${d.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'America/New_York',
  })} ET`;
}

/** "Nov 18". */
export function shortDay(d: Date): string {
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

/** "Recession Radar", "Recession Radar and Momentum Sectors", "A, B and 2 more". */
export function joinNames(names: readonly string[]): string {
  if (names.length <= 1) return names[0] ?? '';
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  if (names.length === 3) return `${names[0]}, ${names[1]} and ${names[2]}`;
  return `${names[0]}, ${names[1]} and ${names.length - 2} more`;
}

export interface ProblemText {
  /** "Alpaca rejected the paper keys at 10:38 ET." */
  happened: string;
  /** "Recession Radar can't place orders. Its next rebalance is Nov 18." */
  affects: string;
  /** "Paper keys rejected", for the sidebar and lists. */
  short: string;
}

export function problemText(p: AccountProblem): ProblemText {
  const happened =
    p.reason === 'rejected'
      ? `Alpaca rejected the ${p.kind} keys${p.at ? ` at ${etTime(p.at)}` : ''}${
          p.detail ? ` (${p.detail.replace(/\.$/, '')})` : ''
        }.`
      : `The stored ${p.kind} keys are switched off.`;
  let affects: string;
  if (p.affected.length === 0) {
    affects = `No running session uses the ${p.kind} account, so nothing is held up.`;
  } else {
    const who = joinNames(p.affected);
    affects = `${who} can't place orders until the keys are fixed.`;
    if (p.next) {
      affects += ` The next rebalance is ${p.next.name} on ${shortDay(p.next.at)}.`;
    }
  }
  const label = p.kind === 'paper' ? 'Paper' : 'Live';
  return {
    happened,
    affects,
    short: p.reason === 'rejected' ? `${label} keys rejected` : `${label} keys off`,
  };
}

export interface HealthSummary {
  tone: 'ok' | 'risk' | 'none';
  title: string;
  body: string;
}

/** The one card that opens the Account tab and the settings overview (phone2 A). */
export function healthSummary(h: AccountHealth): HealthSummary {
  const first = h.problems[0];
  if (first) {
    const t = problemText(first);
    const more =
      h.problems.length > 1 ? ` The ${h.problems[1].kind} account needs a look too.` : '';
    return { tone: 'risk', title: t.happened, body: `${t.affects}${more}` };
  }
  if (h.connected.length === 2) {
    return {
      tone: 'ok',
      title: 'Both accounts connected',
      body: 'Paper and live keys are active.',
    };
  }
  if (h.connected.length === 1) {
    const kind = h.connected[0];
    return {
      tone: 'ok',
      title: `Alpaca ${kind} connected`,
      body:
        kind === 'paper'
          ? "Live isn't connected. Paper sessions stay on paper."
          : "Paper isn't connected.",
    };
  }
  return {
    tone: 'none',
    title: 'No broker connected',
    body: "Backtests don't need one. Connect Alpaca paper when you want to run a paper session.",
  };
}

/**
 * Where a monthly counter ends up at this month's pace, or null when it's too early to say.
 * Plain arithmetic: usage so far divided by the days elapsed, times the days in the month.
 */
export function monthForecast(used: number, now: Date): number | null {
  const day = now.getDate();
  if (used <= 0 || day < 2) return null;
  const days = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const elapsed = day - 1 + (now.getHours() * 60 + now.getMinutes()) / 1440;
  if (elapsed <= 0) return null;
  return Math.max(used, Math.round((used / elapsed) * days));
}
