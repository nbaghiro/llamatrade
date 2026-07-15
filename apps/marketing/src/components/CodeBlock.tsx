import type { CodeLine, Tok } from './codeTokens';

/**
 * DSL code-view renderers. Token data + helpers live in `codeTokens.ts`.
 *
 * - <CodeBlock>: the numbered `ol.codeblock` view (block editor code tab + the
 *   DSL example). Line numbers + `white-space: pre` come from the marketing CSS.
 * - <MiniCode>: the compact `.code-mini` block (no line numbers, no
 *   `white-space: pre` — lines are `<div>`s and indentation is baked into the
 *   tokens as non-breaking spaces via `nb`).
 * - <Tokens>: a bare run of colored spans for a single `white-space: pre-wrap`
 *   block (the copilot `.dsl` bubble) where newlines/spaces live in the strings.
 */

function Seg({ tok }: { tok: Tok }) {
  return tok.c ? <span className={tok.c}>{tok.t}</span> : <span>{tok.t}</span>;
}

export function CodeBlock({ lines }: { lines: CodeLine[] }) {
  return (
    <ol className="codeblock">
      {lines.map((line, i) => (
        <li key={i}>
          {line.map((tok, j) => (
            <Seg key={j} tok={tok} />
          ))}
        </li>
      ))}
    </ol>
  );
}

export function MiniCode({ lines, className }: { lines: CodeLine[]; className: string }) {
  return (
    <div className={className}>
      {lines.map((line, i) => (
        <div key={i}>
          {line.map((tok, j) => (
            <Seg key={j} tok={tok} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function Tokens({ segs }: { segs: Tok[] }) {
  return (
    <>
      {segs.map((tok, j) => (
        <Seg key={j} tok={tok} />
      ))}
    </>
  );
}
