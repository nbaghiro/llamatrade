/**
 * Turns the engine's validation errors into problems placed under their line, and into the named
 * checks the save step lists. Pure, so it is tested without an editor.
 */

import { SUPPORTED_METHODS } from '../../../lib/outline';

export interface EngineError {
  line: number;
  column: number;
  message: string;
}

export interface ProblemChoice {
  label: string;
  from: number;
  to: number;
  insert: string;
}

export interface CodeProblem {
  /** 1-based line, or 0 when the engine gave no line. */
  line: number;
  title: string;
  body: string;
  choices: ProblemChoice[];
  /** Character range of the offending word, for the underline. */
  mark: { from: number; to: number } | null;
}

/** Kebab-case spellings of the methods the engine runs, as written in code. */
export const SUPPORTED_METHOD_WORDS: readonly string[] = SUPPORTED_METHODS.map((m) =>
  m.replace(/_/g, '-')
);

/** "line 6, column 12: strategy.children[0].method: market-cap ..." → "market-cap ...". */
export function cleanMessage(message: string): string {
  let m = message.replace(/^line \d+(, column \d+)?:\s*/i, '');
  m = m.replace(/^[a-z_][\w.[\]]*:\s+/i, (prefix) => (/[.[]/.test(prefix) ? '' : prefix));
  return m ? m[0].toUpperCase() + m.slice(1) : m;
}

function lineStart(text: string, line: number): number {
  let pos = 0;
  for (let i = 1; i < line; i++) {
    const next = text.indexOf('\n', pos);
    if (next < 0) return -1;
    pos = next + 1;
  }
  return pos;
}

function lineAt(text: string, line: number): { from: number; text: string } | null {
  if (line < 1) return null;
  const from = lineStart(text, line);
  if (from < 0) return null;
  const end = text.indexOf('\n', from);
  return { from, text: text.slice(from, end < 0 ? text.length : end) };
}

const METHOD_RE = /:method\s+([a-z][a-z-]*)/i;

function methodTitle(word: string): string {
  const name = word.replace(/-/g, ' ');
  return `${name[0].toUpperCase()}${name.slice(1)} weighting can’t run`;
}

/** Places each engine error under its line, offering supported methods for an unsupported one. */
export function codeProblems(code: string, errors: readonly EngineError[]): CodeProblem[] {
  const out: CodeProblem[] = [];
  for (const err of errors) {
    const message = cleanMessage(err.message);
    const at = lineAt(code, err.line);
    const method = at ? METHOD_RE.exec(at.text) : null;
    const word = method?.[1].toLowerCase();
    if (at && method && word && !SUPPORTED_METHOD_WORDS.includes(word)) {
      const from = at.from + (method.index ?? 0) + method[0].length - method[1].length;
      const to = from + method[1].length;
      out.push({
        line: err.line,
        title: methodTitle(word),
        body:
          word === 'market-cap'
            ? 'It needs company fundamentals, which the engine doesn’t have. Choose a method it supports:'
            : 'The engine doesn’t know this method. Choose one it supports:',
        choices: SUPPORTED_METHOD_WORDS.map((m) => ({ label: m, from, to, insert: m })),
        mark: { from, to },
      });
      continue;
    }
    out.push({
      line: at ? err.line : 0,
      title: message || 'The engine can’t run this line',
      body: '',
      choices: [],
      mark: null,
    });
  }
  const seen = new Set<string>();
  return out.filter((p) => {
    const key = `${p.line}:${p.title}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export type CheckState = 'pass' | 'fail' | 'pending';

export interface NamedCheck {
  name: string;
  state: CheckState;
  detail: string;
}

export interface CheckContext {
  methods: readonly string[];
  symbols: readonly string[];
  indicators: readonly string[];
}

const CATEGORIES: ReadonlyArray<{
  name: string;
  test: RegExp;
  detail: (c: CheckContext) => string;
}> = [
  {
    name: 'Parses',
    test: /pars|syntax|unexpected|expected|unbalanced|unterminated|bracket|paren/i,
    detail: () => '',
  },
  {
    name: 'Every weight method is supported',
    test: /weight|method/i,
    detail: (c) => c.methods.join(', '),
  },
  {
    name: 'Every symbol is valid',
    test: /symbol|ticker|asset/i,
    detail: (c) => c.symbols.join(' '),
  },
  {
    name: 'Indicators are known',
    test: /indicator|period|lookback/i,
    detail: (c) => (c.indicators.length ? c.indicators.join(', ') : 'none used'),
  },
];

/**
 * The engine's verdict grouped into named checks. A check fails when one of the engine's errors
 * is about it; errors that fit no group fail the last check, so nothing is dropped.
 */
export function namedChecks(
  errors: readonly EngineError[] | null,
  ctx: CheckContext
): NamedCheck[] {
  if (errors === null) {
    return CATEGORIES.map((c) => ({ name: c.name, state: 'pending' as const, detail: 'checking' }));
  }
  const buckets = CATEGORIES.map(() => [] as string[]);
  const other: string[] = [];
  for (const e of errors) {
    const msg = cleanMessage(e.message);
    const i = CATEGORIES.findIndex((c) => c.test.test(msg));
    if (i >= 0) buckets[i].push(msg);
    else other.push(msg);
  }
  const checks: NamedCheck[] = CATEGORIES.map((c, i) => ({
    name: c.name,
    state: buckets[i].length ? 'fail' : 'pass',
    detail: buckets[i].length ? buckets[i][0] : c.detail(ctx),
  }));
  if (other.length) checks.push({ name: 'Other checks', state: 'fail', detail: other[0] });
  return checks;
}
