import { blockForms, readForms, rowRanges, type LineRange } from '@llamatrade/core/strategy/forms';
import { hasChildren, type BlockId, type StrategyTree } from '@llamatrade/core/strategy/types';

import { buildOutline, type OutlineLine } from '../../../lib/outline';

export interface SplitRow {
  key: string;
  kind: 'settings' | 'rule';
  /** The rule lines in words, each followed by the holdings directly under it. */
  lines: OutlineLine[];
  blockIds: BlockId[];
  code: LineRange;
}

/** The tree's blocks in reading order, without the root. */
export function blockOrder(tree: StrategyTree): BlockId[] {
  const out: BlockId[] = [];
  const visit = (id: BlockId) => {
    const block = tree.blocks[id];
    if (!block) return;
    if (block.type !== 'root') out.push(id);
    if (hasChildren(block)) block.childIds.forEach(visit);
  };
  visit(tree.rootId);
  return out;
}

/** Each block's first code line, or null when the code's block forms don't line up with the tree. */
export function blockLines(tree: StrategyTree, code: string): Map<BlockId, number> | null {
  const order = blockOrder(tree);
  const forms = blockForms(readForms(code));
  if (forms.length !== order.length) return null;
  const out = new Map<BlockId, number>();
  for (let i = 0; i < order.length; i++) {
    const block = tree.blocks[order[i]];
    if (!block || block.type !== forms[i].head) return null;
    out.set(order[i], forms[i].startLine);
  }
  return out;
}

/**
 * Pairs each rule in words with the code lines it becomes: a settings row first, then one
 * row per rule with its holdings inside it. Returns null when the code's block forms don't
 * line up with the tree, for example while the code is mid-edit.
 */
export function splitRows(tree: StrategyTree, code: string): SplitRow[] | null {
  const startLine = blockLines(tree, code);
  if (!startLine) return null;

  const groups: { anchor: number; lines: OutlineLine[] }[] = [];
  for (const line of buildOutline(tree)) {
    const anchor = startLine.get(line.blockId);
    if (anchor === undefined) continue;
    const last = groups[groups.length - 1];
    if (line.kind === 'asset' && last) {
      last.lines.push(line);
    } else if (last && last.anchor === anchor) {
      last.lines.push(line);
    } else {
      groups.push({ anchor, lines: [line] });
    }
  }

  const total = code === '' ? 1 : code.split('\n').length;
  const firstBlock = groups[0]?.anchor ?? total + 1;
  const hasSettings = firstBlock > 1;
  const anchors = [...(hasSettings ? [1] : []), ...groups.map((g) => g.anchor)];
  const ranges = rowRanges(anchors, total);

  const rows: SplitRow[] = [
    {
      key: 'settings',
      kind: 'settings',
      lines: [],
      blockIds: [],
      code: hasSettings ? ranges[0] : { from: 1, to: 0 },
    },
  ];
  groups.forEach((g, i) => {
    rows.push({
      key: g.lines[0].key,
      kind: 'rule',
      lines: g.lines,
      blockIds: g.lines.map((l) => l.blockId),
      code: ranges[i + (hasSettings ? 1 : 0)],
    });
  });
  return rows;
}

export type CodeTokenKind = 'head' | 'keyword' | 'string' | 'number' | 'paren' | 'text';

/** A light tokenisation of one code line for read-only colouring. */
export function codeTokens(line: string): { kind: CodeTokenKind; text: string }[] {
  const out: { kind: CodeTokenKind; text: string }[] = [];
  const re =
    /("(?:[^"\\]|\\.)*"?)|(\(\s*)([^\s()";]+)?|(\))|(:[^\s()";]+)|(-?\d+(?:\.\d+)?)(?![\w-])|(\s+|[^\s()":]+|.)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line)) !== null) {
    if (m[1] !== undefined) out.push({ kind: 'string', text: m[1] });
    else if (m[2] !== undefined) {
      out.push({ kind: 'paren', text: m[2] });
      if (m[3]) out.push({ kind: 'head', text: m[3] });
    } else if (m[4] !== undefined) out.push({ kind: 'paren', text: m[4] });
    else if (m[5] !== undefined) out.push({ kind: 'keyword', text: m[5] });
    else if (m[6] !== undefined) out.push({ kind: 'number', text: m[6] });
    else if (m[7] !== undefined) {
      const prev = out[out.length - 1];
      if (prev && prev.kind === 'text') prev.text += m[7];
      else out.push({ kind: 'text', text: m[7] });
    }
  }
  return out;
}
