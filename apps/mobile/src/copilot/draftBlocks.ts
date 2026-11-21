/** A drafted strategy's outline as the blocks the draft screen shows (copilot/draft2 C). */
import { blockAuthor, type BlockAuthor } from './draftQuestions.ts';

export interface OutlineInput {
  depth: number;
  kind: 'rule' | 'otherwise' | 'weight' | 'group' | 'funds';
  text: string;
}

export interface DraftBlock {
  label: string;
  value: string;
  author: BlockAuthor;
}

const HEADS: ReadonlySet<OutlineInput['kind']> = new Set(['rule', 'otherwise', 'group']);

function cadenceText(rebalance: string, benchmark: string): string {
  const r = rebalance.trim();
  const head = r ? r[0].toUpperCase() + r.slice(1).toLowerCase() : '';
  if (!head) return benchmark ? `Against ${benchmark}` : '';
  return benchmark ? `${head}, against ${benchmark}` : head;
}

/**
 * One block per rule, "otherwise" or group, holding the weights and funds directly under it;
 * funds or weights outside any rule get a block of their own. The rebalance comes first.
 */
export function draftBlocks(
  lines: readonly OutlineInput[],
  meta: { rebalance: string; benchmark: string },
  personWords: readonly string[],
): DraftBlock[] {
  const out: DraftBlock[] = [];
  const cadence = cadenceText(meta.rebalance, meta.benchmark);
  if (cadence) out.push({ label: 'Rebalance', value: cadence, author: blockAuthor(cadence, personWords) });
  const used = new Set<number>();
  lines.forEach((line, i) => {
    if (used.has(i)) return;
    if (HEADS.has(line.kind)) {
      const parts: string[] = [];
      for (let j = i + 1; j < lines.length; j++) {
        const next = lines[j];
        if (next.depth <= line.depth || HEADS.has(next.kind)) break;
        if (next.depth === line.depth + 1) {
          parts.push(next.kind === 'funds' ? `Hold ${next.text}` : next.text);
          used.add(j);
        }
      }
      const value = parts.join(' · ');
      out.push({ label: line.text, value, author: blockAuthor(`${line.text} ${value}`, personWords) });
      return;
    }
    const value = line.kind === 'funds' ? `Hold ${line.text}` : line.text;
    out.push({ label: line.kind === 'funds' ? 'Holds' : 'Weights', value, author: blockAuthor(value, personWords) });
  });
  return out;
}
