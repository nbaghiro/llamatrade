// A light structural reading of strategy code: every parenthesised form with its head,
// position and keywords. It tolerates unfinished code, so the editor can say where the
// cursor sits while the text is still being typed.

import { DSL_BLOCK_TYPE_SET } from "./vocabulary";

export interface CodeForm {
  head: string;
  /** Offset of the opening parenthesis. */
  start: number;
  /** Offset just past the closing parenthesis, or the text length when unclosed. */
  end: number;
  /** 1-based lines of the opening and closing parenthesis. */
  startLine: number;
  endLine: number;
  /** Index of the enclosing form in the list, or -1. */
  parent: number;
  /** Keywords written directly in this form, without the colon, in order. */
  keywords: string[];
  /** Number of directly nested block forms (weight, asset, group, if, else, filter). */
  blockChildren: number;
  closed: boolean;
}

/** Every form in document order (by opening parenthesis). */
export function readForms(code: string): CodeForm[] {
  const forms: CodeForm[] = [];
  const stack: number[] = [];
  let line = 1;
  let i = 0;
  const n = code.length;
  while (i < n) {
    const ch = code[i];
    if (ch === "\n") {
      line++;
      i++;
    } else if (ch === ";") {
      while (i < n && code[i] !== "\n") i++;
    } else if (ch === '"') {
      i++;
      while (i < n && code[i] !== '"') {
        if (code[i] === "\\") i++;
        else if (code[i] === "\n") line++;
        i++;
      }
      i++;
    } else if (ch === "(") {
      let j = i + 1;
      while (j < n && /\s/.test(code[j]) && code[j] !== "\n") j++;
      let k = j;
      while (k < n && !/[\s()";]/.test(code[k])) k++;
      const parent = stack.length ? stack[stack.length - 1] : -1;
      forms.push({
        head: code.slice(j, k),
        start: i,
        end: n,
        startLine: line,
        endLine: line,
        parent,
        keywords: [],
        blockChildren: 0,
        closed: false,
      });
      stack.push(forms.length - 1);
      i++;
    } else if (ch === ")") {
      const idx = stack.pop();
      if (idx !== undefined) {
        const f = forms[idx];
        f.end = i + 1;
        f.endLine = line;
        f.closed = true;
        if (f.parent >= 0 && DSL_BLOCK_TYPE_SET.has(f.head) && f.head !== "strategy") {
          forms[f.parent].blockChildren++;
        }
      }
      i++;
    } else if (ch === ":") {
      let k = i + 1;
      while (k < n && !/[\s()";]/.test(code[k])) k++;
      const top = stack[stack.length - 1];
      if (top !== undefined && k > i + 1) forms[top].keywords.push(code.slice(i + 1, k));
      i = k;
    } else {
      i++;
    }
  }
  for (const idx of stack) {
    forms[idx].endLine = line;
  }
  for (const f of forms) {
    if (!f.closed && f.parent >= 0 && DSL_BLOCK_TYPE_SET.has(f.head) && f.head !== "strategy") {
      forms[f.parent].blockChildren++;
    }
  }
  return forms;
}

/** The chain of forms that contain `offset`, outermost first. */
export function formPathAt(forms: readonly CodeForm[], offset: number): CodeForm[] {
  let idx = -1;
  forms.forEach((f, i) => {
    if (f.start < offset && offset < f.end + (f.closed ? 0 : 1)) idx = i;
  });
  const path: CodeForm[] = [];
  while (idx >= 0) {
    path.unshift(forms[idx]);
    idx = forms[idx].parent;
  }
  return path;
}

/** Block forms only (the ones that become blocks in the outline), in document order. */
export function blockForms(forms: readonly CodeForm[]): CodeForm[] {
  return forms.filter((f) => DSL_BLOCK_TYPE_SET.has(f.head) && f.head !== "strategy");
}

export interface LineRange {
  from: number;
  to: number;
}

/**
 * Splits code into row ranges, one per anchor, for printing words beside code. Each
 * anchor owns the lines from its first line up to the line before the next anchor; the
 * first range also takes any lines before it. `anchors` are 1-based start lines,
 * ascending; `total` is the line count.
 */
export function rowRanges(anchors: readonly number[], total: number): LineRange[] {
  const out: LineRange[] = [];
  for (let i = 0; i < anchors.length; i++) {
    const from = i === 0 ? 1 : anchors[i];
    const to = i + 1 < anchors.length ? anchors[i + 1] - 1 : total;
    out.push({ from, to: Math.max(from, to) });
  }
  return out;
}
