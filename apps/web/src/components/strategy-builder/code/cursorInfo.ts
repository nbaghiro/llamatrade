import { formPathAt, type CodeForm } from '@llamatrade/core/strategy/forms';
import { DSL_BLOCK_TYPE_SET, DSL_KEYWORDS_BY_FORM } from '@llamatrade/core/strategy/vocabulary';

export interface KeywordValue {
  name: string;
  value: string;
}

/** The keywords written directly in a form, each with the value that follows it. */
export function keywordValues(code: string, form: CodeForm): KeywordValue[] {
  const out: KeywordValue[] = [];
  const end = Math.min(form.end, code.length);
  let depth = 0;
  let i = form.start + 1;
  const skipString = (k: number) => {
    let j = k + 1;
    while (j < end && code[j] !== '"') j += code[j] === '\\' ? 2 : 1;
    return j + 1;
  };
  while (i < end) {
    const ch = code[i];
    if (ch === '"') {
      i = skipString(i);
    } else if (ch === '(') {
      depth++;
      i++;
    } else if (ch === ')') {
      depth--;
      i++;
    } else if (ch === ':' && depth === 0) {
      let k = i + 1;
      while (k < end && !/[\s()";]/.test(code[k])) k++;
      const name = code.slice(i + 1, k);
      while (k < end && /\s/.test(code[k])) k++;
      let v = k;
      if (code[k] === '"') {
        v = skipString(k);
      } else if (code[k] === '(') {
        let d = 0;
        for (; v < end; v++) {
          if (code[v] === '(') d++;
          else if (code[v] === ')' && --d === 0) {
            v++;
            break;
          }
        }
      } else {
        while (v < end && !/[\s()";:]/.test(code[v])) v++;
      }
      if (name) out.push({ name, value: code.slice(k, v).trim() });
      i = Math.max(v, k, i + 1);
    } else {
      i++;
    }
  }
  return out;
}

const isBlock = (f: CodeForm) => DSL_BLOCK_TYPE_SET.has(f.head);

type KeywordForm = keyof typeof DSL_KEYWORDS_BY_FORM;
const hasKeywords = (head: string): head is KeywordForm => head in DSL_KEYWORDS_BY_FORM;

/** The keywords a form accepts, with the colon. */
export function acceptedKeywords(head: string): string[] {
  return hasKeywords(head) ? DSL_KEYWORDS_BY_FORM[head].map((k) => `:${k}`) : [];
}

const ROLE: Record<string, string> = {
  strategy: 'Settings for the whole strategy and its top block.',
  weight: 'It decides how its children share the money.',
  asset: 'One holding.',
  group: 'A named set of holdings that takes one share.',
  filter: 'It ranks its children and keeps some of them.',
  if: 'It holds its first block while the condition is true.',
  else: 'It holds its block when the condition above is false.',
};

function placeOf(parent: CodeForm | undefined): string {
  if (!parent) return 'at the top level';
  switch (parent.head) {
    case 'strategy':
      return 'at the top of the strategy';
    case 'if':
      return 'on the when side';
    case 'else':
      return 'on the otherwise side';
    default:
      return `inside a ${parent.head}`;
  }
}

export interface CursorInfo {
  /** Block forms from the outermost in, for the breadcrumb. */
  crumbs: string[];
  /** The innermost block form, if any. */
  form: CodeForm | null;
  /** "weight", placed: "inside the otherwise side". */
  place: string;
  role: string;
  accepts: string[];
  set: KeywordValue[];
  missing: string[];
  children: string;
}

function childrenLabel(forms: readonly CodeForm[], index: number): string {
  const heads = forms.filter((f) => f.parent === index && isBlock(f)).map((f) => f.head);
  if (heads.length === 0) return 'None';
  if (heads.every((h) => h === 'asset')) {
    return `${heads.length} ${heads.length === 1 ? 'asset' : 'assets'}`;
  }
  return `${heads.length} ${heads.length === 1 ? 'block' : 'blocks'}`;
}

/** What the editor knows about the place the cursor sits in. */
export function cursorInfo(code: string, forms: readonly CodeForm[], offset: number): CursorInfo {
  const path = formPathAt(forms, offset).filter(isBlock);
  const form = path[path.length - 1] ?? null;
  if (!form) {
    return {
      crumbs: [],
      form: null,
      place: '',
      role: '',
      accepts: [],
      set: [],
      missing: [],
      children: 'None',
    };
  }
  const accepts = acceptedKeywords(form.head);
  const set = keywordValues(code, form);
  const present = new Set(set.map((k) => `:${k.name}`));
  return {
    crumbs: path.map((f) => f.head),
    form,
    place: placeOf(path[path.length - 2]),
    role: ROLE[form.head] ?? '',
    accepts,
    set,
    missing: accepts.filter((k) => !present.has(k)),
    children: childrenLabel(forms, forms.indexOf(form)),
  };
}

/** DSL_KEYWORDS_BY_FORM with forms that accept the same keywords merged into one row. */
export function keywordRows(): { forms: string; keywords: string }[] {
  const rows = new Map<string, string[]>();
  for (const [form, keys] of Object.entries(DSL_KEYWORDS_BY_FORM)) {
    const k = keys.map((x) => `:${x}`).join(' ');
    rows.set(k, [...(rows.get(k) ?? []), form]);
  }
  return [...rows.entries()].map(([keywords, list]) => ({ forms: list.join(', '), keywords }));
}

/** "recession-radar.lt" from a strategy name. */
export function fileName(name: string): string {
  const slug = (name || 'strategy')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return `${slug || 'strategy'}.lt`;
}
