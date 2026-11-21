import { blockForms, readForms } from '@llamatrade/core/strategy/forms';
import { hasChildren, type BlockId, type StrategyTree } from '@llamatrade/core/strategy/types';

/** Block ids in the order their forms are written: a pre-order walk without the root. */
function writtenOrder(tree: StrategyTree): BlockId[] {
  const out: BlockId[] = [];
  const walk = (id: BlockId) => {
    const b = tree.blocks[id];
    if (!b) return;
    if (b.type !== 'root') out.push(id);
    if (hasChildren(b)) b.childIds.forEach(walk);
  };
  walk(tree.rootId);
  return out;
}

const oneLine = (s: string) => s.replace(/\s+/g, ' ').trim();

/**
 * The code each block was written as, shortened to its head: "(if (> (rsi SPY 14) 70) …)",
 * "(asset TLT :weight 60)". Empty when the code and the tree don't line up.
 */
export function codeFragments(code: string, tree: StrategyTree): Map<BlockId, string> {
  const forms = readForms(code);
  const blocks = blockForms(forms);
  const order = writtenOrder(tree);
  const out = new Map<BlockId, string>();
  if (blocks.length !== order.length) return out;
  for (let i = 0; i < order.length; i++) {
    const form = blocks[i];
    const block = tree.blocks[order[i]];
    if (!block || form.head !== block.type) return new Map();
    const idx = forms.indexOf(form);
    const kids = forms.filter((f) => f.parent === idx);
    let head: string;
    if (block.type === 'if' && kids[0]) {
      head = code.slice(form.start, kids[0].end);
    } else {
      const firstBlockChild = kids.find((k) => blocks.includes(k));
      head = code.slice(form.start, firstBlockChild ? firstBlockChild.start : form.end);
    }
    const whole = head.length >= form.end - form.start;
    out.set(block.id, whole ? oneLine(head) : `${oneLine(head)} …)`);
  }
  return out;
}
