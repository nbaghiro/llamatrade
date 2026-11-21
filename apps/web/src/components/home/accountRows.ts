/** Home's account as tree rows: account, live and paper, each session, then its strategy's rules and holdings. */

import type { StrategyTree } from '@llamatrade/core/strategy/types';

import { buildOutline, type OutlineLineKind, type OutlinePart } from '../../lib/outline';
import { heldPath } from '../../lib/outlineTree';

import { dayLabel, etDay, nextRebalance, type HomeSession } from './homeModel';

export interface HeldValue {
  symbol: string;
  value: number;
}

export interface SessionSource {
  strategyId: string;
  version: number;
  tree: StrategyTree | null;
  positions: readonly HeldValue[];
}

export type HomeRowKind = 'account' | 'mode' | 'session' | 'rule' | 'asset' | 'other';

export interface HomeRow {
  id: string;
  depth: number;
  type: string;
  kind: HomeRowKind;
  label?: string;
  /** Quieter words after the label. */
  sub?: string;
  /** A rule's sentence, from the strategy outline. */
  parts?: OutlinePart[];
  outlineKind?: OutlineLineKind;
  symbol?: string;
  /** Percent of the row's parent. */
  share?: number;
  value?: number;
  today?: number | null;
  /** Said in place of today's change, e.g. "Final value". */
  na?: string;
  note?: string;
  /** On the path the session holds today. */
  live: boolean;
  /** The branch in effect today, marked at the row's end. */
  liveMarker?: boolean;
  muted?: boolean;
  warn?: boolean;
  href?: string;
  sessionId?: string;
  /** Which line the chart draws while the row is hovered or kept. */
  lineKey?: string;
}

export const ACCOUNT_LINE = 'account';
export const modeLine = (mode: string) => `mode:${mode}`;
export const sessionLine = (id: string) => `session:${id}`;

const done = (s: HomeSession) => s.state === 'stopped' || s.state === 'error';
const pctOf = (part: number, whole: number) => (whole > 0 ? (part / whole) * 100 : undefined);

function sessionSub(s: HomeSession, version: number | null): string {
  if (done(s)) return s.stoppedAt ? `stopped ${dayLabel(etDay(s.stoppedAt))}` : 'stopped';
  const v = version ? `v${version}, ` : '';
  if (s.state === 'frozen')
    return s.frozenAt ? `${v}frozen since ${dayLabel(etDay(s.frozenAt))}` : `${v}frozen`;
  if (s.state === 'paused') return `${v}paused`;
  return s.startedAt ? `${v}since ${dayLabel(etDay(s.startedAt))}` : `${v}running`;
}

/** The rows a running session's strategy adds under it, with what it holds on each holding. */
function strategyRows(s: HomeSession, src: SessionSource, depth: number, today: Date): HomeRow[] {
  const held = new Map<string, number>();
  for (const p of src.positions) held.set(p.symbol, (held.get(p.symbol) ?? 0) + p.value);
  const sessionValue = s.value ?? [...held.values()].reduce((a, v) => a + v, 0);
  const href = `/strategies/${src.strategyId}/edit`;
  const out: HomeRow[] = [];
  const shown = new Set<string>();
  const asset = (id: string, symbol: string, d: number, live: boolean): HomeRow => {
    const value = held.get(symbol);
    return {
      id,
      depth: d,
      type: 'Asset',
      kind: 'asset',
      symbol,
      live: live && value !== undefined,
      muted: value === undefined,
      share: value === undefined ? undefined : pctOf(value, sessionValue),
      value,
      sessionId: s.id,
    };
  };
  if (src.tree) {
    const live = heldPath(src.tree, new Set(held.keys()));
    const next = nextRebalance(s.rebalance, today);
    let noted = false;
    for (const line of buildOutline(src.tree)) {
      const id = `${s.id}:${line.key}`;
      const d = depth + line.depth;
      const on = live.has(line.blockId);
      if (line.kind === 'asset' && line.symbol) {
        shown.add(line.symbol);
        out.push({ ...asset(id, line.symbol, d, on), label: line.name });
        continue;
      }
      if (line.kind === 'collapsed') continue;
      const top =
        line.depth === 0 && !noted && next !== null && line.kind !== 'if' && line.kind !== 'else';
      if (top) noted = true;
      out.push({
        id,
        depth: d,
        type: line.kind === 'else' ? 'Else' : `${line.kind[0].toUpperCase()}${line.kind.slice(1)}`,
        kind: 'rule',
        outlineKind: line.kind,
        parts: line.parts,
        live: on,
        liveMarker: on && (line.kind === 'if' || line.kind === 'else'),
        muted: live.size > 0 && !on && line.kind === 'else',
        note: top && next ? `Next rebalance ${dayLabel(next)}` : undefined,
        href,
        sessionId: s.id,
        lineKey: sessionLine(s.id),
      });
    }
  }
  for (const [symbol] of [...held].sort((a, b) => b[1] - a[1])) {
    if (!shown.has(symbol)) out.push(asset(`${s.id}:held:${symbol}`, symbol, depth, true));
  }
  return out;
}

export interface AccountInput {
  sessions: readonly HomeSession[];
  sources: ReadonlyMap<string, SessionSource>;
  total: number;
  today: number | null;
  day: Date;
}

export function accountRows({ sessions, sources, total, today, day }: AccountInput): HomeRow[] {
  const out: HomeRow[] = [
    {
      id: 'account',
      depth: 0,
      type: 'Account',
      kind: 'account',
      label: 'All accounts',
      live: false,
      value: total,
      today,
      lineKey: ACCOUNT_LINE,
    },
  ];
  let inSessions = 0;
  for (const mode of ['live', 'paper'] as const) {
    const inMode = sessions
      .filter((s) => s.mode === mode)
      .sort((a, b) => Number(done(a)) - Number(done(b)) || (b.value ?? 0) - (a.value ?? 0));
    if (inMode.length === 0) continue;
    const value = inMode.reduce((a, s) => a + (s.value ?? 0), 0);
    inSessions += value;
    const running = inMode.filter((s) => !done(s)).length;
    const todays = inMode.filter((s) => !done(s) && s.today !== null);
    out.push({
      id: mode,
      depth: 1,
      type: mode === 'live' ? 'Live' : 'Paper',
      kind: 'mode',
      label: mode === 'live' ? 'Live account' : 'Paper account',
      sub: `${running} running`,
      live: false,
      share: pctOf(value, total),
      value,
      today: todays.length ? todays.reduce((a, s) => a + (s.today ?? 0), 0) : null,
      lineKey: modeLine(mode),
    });
    for (const s of inMode) {
      const src = sources.get(s.id);
      const kids = src && !done(s) ? strategyRows(s, src, 3, day) : [];
      out.push({
        id: s.id,
        depth: 2,
        type: 'Session',
        kind: 'session',
        label: s.name,
        sub: sessionSub(s, src?.version ?? null),
        live: kids.some((k) => k.live),
        muted: done(s),
        warn: s.state === 'frozen',
        share: s.value === null ? undefined : pctOf(s.value, value),
        value: s.value ?? undefined,
        today: done(s) ? undefined : s.today,
        na: done(s) ? 'Final value' : undefined,
        href: s.href,
        sessionId: s.id,
        lineKey: sessionLine(s.id),
      });
      out.push(...kids);
    }
  }
  const outside = total - inSessions;
  if (inSessions > 0 && outside >= 0.5) {
    out.push({
      id: 'outside',
      depth: 1,
      type: 'Other',
      kind: 'other',
      label: 'Not in a session',
      live: false,
      muted: true,
      share: pctOf(outside, total),
      value: outside,
      na: '',
    });
  }
  return out;
}
