/** A small reader for strategy code that keeps each atom's position, so one value can be replaced in place. */

export interface Atom {
  kind: 'atom';
  text: string;
  start: number;
  end: number;
}

export interface Str {
  kind: 'string';
  text: string;
  start: number;
  end: number;
}

export interface List {
  kind: 'list';
  items: Node[];
  start: number;
  end: number;
}

export type Node = Atom | Str | List;

/** Every top-level form in the code. Unclosed lists end at the end of the text. */
export function readCode(code: string): Node[] {
  const out: Node[] = [];
  const stack: List[] = [];
  const push = (n: Node) => {
    const top = stack[stack.length - 1];
    if (top) top.items.push(n);
    else out.push(n);
  };
  let i = 0;
  const n = code.length;
  while (i < n) {
    const ch = code[i];
    if (/\s/.test(ch)) {
      i++;
    } else if (ch === ';') {
      while (i < n && code[i] !== '\n') i++;
    } else if (ch === '(') {
      const list: List = { kind: 'list', items: [], start: i, end: n };
      push(list);
      stack.push(list);
      i++;
    } else if (ch === ')') {
      const list = stack.pop();
      if (list) list.end = i + 1;
      i++;
    } else if (ch === '"') {
      const start = i;
      let text = '';
      i++;
      while (i < n && code[i] !== '"') {
        if (code[i] === '\\' && i + 1 < n) {
          text += code[i + 1];
          i += 2;
        } else {
          text += code[i];
          i++;
        }
      }
      i++;
      push({ kind: 'string', text, start, end: Math.min(i, n) });
    } else {
      const start = i;
      while (i < n && !/[\s()";]/.test(code[i])) i++;
      push({ kind: 'atom', text: code.slice(start, i), start, end: i });
    }
  }
  return out;
}

export function isList(n: Node | undefined): n is List {
  return n?.kind === 'list';
}

export function isAtom(n: Node | undefined): n is Atom {
  return n?.kind === 'atom';
}

/** The head atom of a list, lowercased, or ''. */
export function headOf(n: Node | undefined): string {
  return isList(n) && isAtom(n.items[0]) ? n.items[0].text.toLowerCase() : '';
}

/** The node after `:key` in a list, if any. */
export function keyword(list: List, key: string): Node | undefined {
  const i = list.items.findIndex((x) => isAtom(x) && x.text === `:${key}`);
  return i >= 0 ? list.items[i + 1] : undefined;
}

/** The list's positional children: every item after the head that is not a keyword or its value. */
export function children(list: List): Node[] {
  const out: Node[] = [];
  for (let i = 1; i < list.items.length; i++) {
    const x = list.items[i];
    if (isAtom(x) && x.text.startsWith(':')) {
      i++;
      continue;
    }
    out.push(x);
  }
  return out;
}

export function isNumber(text: string): boolean {
  return /^-?\d+(\.\d+)?$/.test(text);
}
