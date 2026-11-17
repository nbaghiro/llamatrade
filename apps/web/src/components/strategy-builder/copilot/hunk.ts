import type { CodeLine } from '../../../lib/strategyDiff';

/** The changed lines with one line of context each side. */
export function changedHunk(lines: readonly CodeLine[]): CodeLine[] {
  const keep = new Set<number>();
  lines.forEach((l, i) => {
    if (l.kind === 'same') return;
    for (let k = i - 1; k <= i + 1; k++) if (k >= 0 && k < lines.length) keep.add(k);
  });
  return lines.filter((_, i) => keep.has(i));
}
