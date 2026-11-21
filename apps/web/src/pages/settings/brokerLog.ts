import type { AccountKind } from './health';
import { maskedKey } from './model';

/** A check run from this browser, kept on this device because the API stores none. */
export interface BrowserCheck {
  at: Date;
  isPaper: boolean;
  valid: boolean;
}

export interface BrokerEvent {
  id: string;
  at: Date;
  kind: AccountKind | 'both';
  text: string;
  /** Right-hand note: how it happened or who did it. */
  note: string;
  tone: 'ok' | 'risk' | 'plain';
}

export interface LogCredential {
  id: string;
  isPaper: boolean;
  apiKeyPrefix: string;
  createdAt: Date | null;
}

export interface LogSession {
  id: string;
  name: string;
  kind: AccountKind;
  endedAt: Date | null;
}

const label = (kind: AccountKind) => (kind === 'paper' ? 'Paper' : 'Live');
const kindOf = (isPaper: boolean): AccountKind => (isPaper ? 'paper' : 'live');

/** What the app can honestly list: connections, stopped sessions and checks from this browser. */
export function brokerEvents(
  credentials: readonly LogCredential[],
  checks: readonly BrowserCheck[],
  sessions: readonly LogSession[]
): BrokerEvent[] {
  const events: BrokerEvent[] = [];
  for (const c of credentials) {
    if (!c.createdAt) continue;
    const kind = kindOf(c.isPaper);
    events.push({
      id: `connected-${c.id}`,
      at: c.createdAt,
      kind,
      text: `${label(kind)} account connected`,
      note: c.apiKeyPrefix ? `key ${maskedKey(c.apiKeyPrefix)}` : '',
      tone: 'ok',
    });
  }
  for (const s of sessions) {
    if (!s.endedAt) continue;
    events.push({
      id: `stopped-${s.id}`,
      at: s.endedAt,
      kind: s.kind,
      text: `${s.name} stopped on ${s.kind}`,
      note: '',
      tone: 'plain',
    });
  }
  checks.forEach((c, i) => {
    const kind = kindOf(c.isPaper);
    events.push({
      id: `check-${c.at.getTime()}-${i}`,
      at: c.at,
      kind,
      text: `${label(kind)} keys ${c.valid ? 'accepted' : 'rejected'} by Alpaca`,
      note: 'checked from this browser',
      tone: c.valid ? 'ok' : 'risk',
    });
  });
  return events.sort((a, b) => b.at.getTime() - a.at.getTime());
}

export type LogFilter = 'all' | AccountKind;

export function filterEvents(events: readonly BrokerEvent[], filter: LogFilter): BrokerEvent[] {
  return filter === 'all' ? [...events] : events.filter((e) => e.kind === filter);
}

const KEY = 'llamatrade-broker-checks';
const KEEP = 50;

export function parseChecks(raw: string | null): BrowserCheck[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.flatMap((item: unknown) => {
      if (typeof item !== 'object' || item === null) return [];
      const { at, isPaper, valid } = item as Record<string, unknown>;
      const when = typeof at === 'string' ? new Date(at) : null;
      if (!when || Number.isNaN(when.getTime())) return [];
      if (typeof isPaper !== 'boolean' || typeof valid !== 'boolean') return [];
      return [{ at: when, isPaper, valid }];
    });
  } catch {
    return [];
  }
}

export function readChecks(): BrowserCheck[] {
  try {
    return parseChecks(window.localStorage.getItem(KEY));
  } catch {
    return [];
  }
}

/** Adds a check to this device's list, newest first, keeping the last fifty. */
export function recordCheck(check: BrowserCheck): BrowserCheck[] {
  const next = [check, ...readChecks()].slice(0, KEEP);
  try {
    window.localStorage.setItem(
      KEY,
      JSON.stringify(next.map((c) => ({ ...c, at: c.at.toISOString() })))
    );
  } catch {
    // Not saved; the check still shows on the page until it reloads.
  }
  return next;
}

/** The line under the Broker heading: how many accounts are connected and the last check here. */
export function brokerHeadline(
  connected: readonly AccountKind[],
  problems: number,
  lastCheck: Date | null,
  etTime: (d: Date) => string
): string {
  const accounts =
    connected.length === 0
      ? 'No Alpaca account connected.'
      : problems > 0
        ? `${problems === 1 ? 'One account needs' : 'Both accounts need'} a look.`
        : connected.length === 2
          ? 'Both accounts connected.'
          : `${label(connected[0])} account connected.`;
  if (connected.length === 0) return accounts;
  return lastCheck
    ? `${accounts} Last checked from this browser at ${etTime(lastCheck)}.`
    : `${accounts} Not checked from this browser yet.`;
}
