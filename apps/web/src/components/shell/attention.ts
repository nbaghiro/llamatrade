import { SleeveStatus, type Sleeve } from '@llamatrade/core/proto/ledger_pb';
import type { FrozenSleeve } from '@llamatrade/core/stores/dashboard';
import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { useEffect, useMemo } from 'react';
import { create } from 'zustand';

import { activeDestination, AREAS, type DestinationKey } from '../../lib/navigation';
import type { AttentionEntry } from '../home/attention';
import { useAttentionEntries } from '../home/useAttentionEntries';

/** Something that needs the person, pinned to the area where it is resolved. */
export interface AreaMark {
  id: string;
  area: DestinationKey;
  title: string;
  href: string;
}

interface ShellAttentionState {
  reported: Record<string, readonly AreaMark[]>;
  report: (source: string, marks: readonly AreaMark[]) => void;
}

/** Marks pages report beyond what the shell reads itself, keyed by the reporting source. */
export const useShellAttention = create<ShellAttentionState>((set) => ({
  reported: {},
  report: (source, marks) => set((s) => ({ reported: { ...s.reported, [source]: marks } })),
}));

/**
 * Puts a page's marks in the bar. The last report from a source stays after the page closes,
 * so a frozen session found on one page is still marked on the next; report [] to clear it.
 */
export function useReportAttention(source: string, marks: readonly AreaMark[]) {
  const report = useShellAttention((s) => s.report);
  const key = marks.map((m) => `${m.id}:${m.area}`).join('|');
  useEffect(() => {
    report(source, marks);
    // `key` captures the marks' identity; the array itself is rebuilt on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, key, report]);
}

/** Frozen and rejected work lives under Sessions (attention2 A); notices go where they link. */
export function entryArea(entry: AttentionEntry): DestinationKey | null {
  if (entry.kind === 'frozen' || entry.kind === 'rejected') return 'sessions';
  return activeDestination(entry.href.split('?')[0], AREAS);
}

/** Frozen sleeves from the trading store, named by their session where one matches. */
export function frozenFromSleeves(
  sleeves: readonly Pick<Sleeve, 'id' | 'name' | 'status' | 'strategyExecutionId'>[]
): FrozenSleeve[] {
  return sleeves
    .filter((s) => s.status === SleeveStatus.FROZEN)
    .map((s) => ({ id: s.id, name: s.name, executionId: s.strategyExecutionId }));
}

/** Every mark by area, the shell's own first, without duplicates. */
export function groupMarks(
  entries: readonly AttentionEntry[],
  reported: Record<string, readonly AreaMark[]>
): Partial<Record<DestinationKey, AreaMark[]>> {
  const out: Partial<Record<DestinationKey, AreaMark[]>> = {};
  const seen = new Set<string>();
  const add = (m: AreaMark) => {
    if (seen.has(m.id)) return;
    seen.add(m.id);
    (out[m.area] ??= []).push(m);
  };
  for (const e of entries) {
    const area = entryArea(e);
    if (area) add({ id: e.id, area, title: e.title, href: e.href });
  }
  for (const marks of Object.values(reported)) marks.forEach(add);
  return out;
}

/**
 * Marks for the bar from what has loaded: Home's attention entries, frozen sleeves the
 * trading store read, and anything pages reported.
 */
export function useAreaMarks(): Partial<Record<DestinationKey, AreaMark[]>> {
  const entries = useAttentionEntries();
  const dashboardFrozen = useDashboardStore((s) => s.frozenSleeves);
  const sleeves = useTradingStore((s) => s.sleeves);
  const reported = useShellAttention((s) => s.reported);
  return useMemo(() => {
    const extra: AttentionEntry[] =
      dashboardFrozen === null
        ? frozenFromSleeves(sleeves).map((f) => ({
            id: `frozen-${f.id}`,
            kind: 'frozen',
            title: `${f.name || 'A sleeve'} is frozen.`,
            detail: '',
            href: '/trading',
          }))
        : [];
    return groupMarks([...entries, ...extra], reported);
  }, [entries, dashboardFrozen, sleeves, reported]);
}

/** Frozen sleeves are carried by the seam, so the nav doesn't flag them again. */
export const isFrozenMark = (m: AreaMark) => m.id.startsWith('frozen-');

/** What the amber seam under the bar says (attention2 B); null when nothing is frozen. */
export interface SeamNotice {
  title: string;
  detail: string;
  href: string;
  /** Further frozen sleeves beyond the one named. */
  more: number;
}

/** The first frozen sleeve, named, with a link to its session or sleeve page. */
export function seamNotice(frozen: readonly FrozenSleeve[]): SeamNotice | null {
  const seen = new Set<string>();
  const unique = frozen.filter((f) => !seen.has(f.id) && seen.add(f.id));
  const first = unique[0];
  if (!first) return null;
  return {
    title: `${first.name || 'A sleeve'} is frozen`,
    detail: "Its holdings don't match Alpaca",
    href: first.executionId
      ? `/trading/${encodeURIComponent(first.executionId)}`
      : `/portfolio/sleeves/${encodeURIComponent(first.id)}`,
    more: unique.length - 1,
  };
}

/** Frozen sleeves from Home's read and the trading store's, for the seam. */
export function useSeamNotice(): SeamNotice | null {
  const dashboardFrozen = useDashboardStore((s) => s.frozenSleeves);
  const sleeves = useTradingStore((s) => s.sleeves);
  return useMemo(
    () => seamNotice([...(dashboardFrozen ?? []), ...frozenFromSleeves(sleeves)]),
    [dashboardFrozen, sleeves]
  );
}
