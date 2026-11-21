import type { BlockId } from '@llamatrade/core/strategy/types';

import { cleanMessage, type EngineError } from '../codemirror/problemModel';

export type CheckSeverity = 'error' | 'warning';

export interface CheckIssue {
  ruleId: string;
  message: string;
  severity: CheckSeverity;
  blockId?: BlockId;
}

export interface CheckItem {
  key: string;
  severity: CheckSeverity;
  /** The validator's or the engine's own words. */
  message: string;
  line: number | null;
  /** A plain sentence on what it means. */
  explain: string;
  blockId: BlockId | null;
  /** Set once the problem is gone from the draft. */
  fixedAt: Date | null;
}

const EXPLAIN: Record<string, string> = {
  'weight.sum':
    'The weights here don’t add up to 100%. Check that each holding has the share you meant.',
  'weight.positive': 'A negative weight means a short position, which may not be what you meant.',
  'weight.specified-missing': 'Every holding under fixed weights needs a share before it can run.',
  'weight.has-children': 'This weight rule has nothing to weight yet.',
  'structure.has-assets': 'The strategy has to hold at least one symbol.',
  'structure.no-duplicates':
    'The same symbol is listed twice here, so weighting or ranking counts it twice.',
  'structure.no-orphans': 'This block isn’t connected to the strategy, so it never runs.',
  'structure.group-not-empty': 'This group holds nothing yet.',
  'condition.required': 'This rule needs a condition to test.',
  'condition.meaningful': 'The condition still has its default values.',
  'condition.has-then': 'The rule needs something to hold when its condition is true.',
  'filter.count-positive': 'A filter has to keep at least one symbol.',
  'filter.count-exceeds': 'The filter asks for more symbols than it has to choose from.',
};

const ENGINE_EXPLAIN = 'The engine can’t run this line as written.';

const LABEL: Record<CheckSeverity, string> = { error: 'Error', warning: 'Warning' };

export function explainIssue(ruleId: string, severity: CheckSeverity): string {
  return `${LABEL[severity]}. ${EXPLAIN[ruleId] ?? 'The validator flagged this rule.'}`;
}

/** The validator's issues and the engine's errors as one list, errors first, each with a line. */
export function checkItems(
  issues: readonly CheckIssue[],
  engineErrors: readonly EngineError[],
  lines: ReadonlyMap<BlockId, number> | null
): CheckItem[] {
  const out: CheckItem[] = [];
  for (const i of issues) {
    out.push({
      key: `${i.severity}|${i.ruleId}|${i.message}`,
      severity: i.severity,
      message: i.message,
      line: (i.blockId && lines?.get(i.blockId)) || null,
      explain: explainIssue(i.ruleId, i.severity),
      blockId: i.blockId ?? null,
      fixedAt: null,
    });
  }
  for (const e of engineErrors) {
    const message = cleanMessage(e.message);
    out.push({
      key: `error|engine|${message}`,
      severity: 'error',
      message,
      line: e.line > 0 ? e.line : null,
      explain: `Error. ${ENGINE_EXPLAIN}`,
      blockId: null,
      fixedAt: null,
    });
  }
  const unique = new Map<string, CheckItem>();
  for (const c of out) if (!unique.has(c.key)) unique.set(c.key, c);
  return [...unique.values()].sort((a, b) =>
    a.severity === b.severity
      ? (a.line ?? Infinity) - (b.line ?? Infinity)
      : a.severity === 'error'
        ? -1
        : 1
  );
}

const FIXED_KEPT = 5;

/**
 * The current checks, followed by earlier ones that are gone, marked fixed at `now`.
 * A fixed check that comes back is listed as open again.
 */
export function withFixed(
  previous: readonly CheckItem[],
  current: readonly CheckItem[],
  now: Date
): CheckItem[] {
  const open = new Set(current.map((c) => c.key));
  const fixed = previous
    .filter((p) => !open.has(p.key))
    .map((p) => (p.fixedAt ? p : { ...p, fixedAt: now }))
    .slice(0, FIXED_KEPT);
  return [...current, ...fixed];
}

export function checkCounts(items: readonly CheckItem[]): { errors: number; warnings: number } {
  const open = items.filter((i) => i.fixedAt === null);
  return {
    errors: open.filter((i) => i.severity === 'error').length,
    warnings: open.filter((i) => i.severity === 'warning').length,
  };
}

/** The first problem line after `from`, wrapping to the top; null when no open problem has a line. */
export function nextProblemLine(items: readonly CheckItem[], from: number): number | null {
  const lines = [
    ...new Set(items.flatMap((i) => (i.fixedAt === null && i.line !== null ? [i.line] : []))),
  ].sort((a, b) => a - b);
  if (lines.length === 0) return null;
  return lines.find((l) => l > from) ?? lines[0];
}

export const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** "1 error, 2 warnings", leaving out a zero count; empty when both are zero. */
export function countsText(c: { errors: number; warnings: number }): string {
  const parts: string[] = [];
  if (c.errors) parts.push(plural(c.errors, 'error', 'errors'));
  if (c.warnings) parts.push(plural(c.warnings, 'warning', 'warnings'));
  return parts.join(', ');
}
