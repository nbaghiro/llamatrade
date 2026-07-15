/**
 * Syntax tokens for the DSL code views (see CodeBlock.tsx). Kept in a separate
 * module from the components so React Fast Refresh stays happy (a file that
 * exports components should export only components).
 *
 * A token is either plain text or a colored span: `.k` keyword/orange,
 * `.s` symbol/green, `.m` muted. Leading-space tokens preserve indentation
 * (via `p` under `white-space: pre`, or `nb` where `pre` is absent).
 */
export type TokClass = 'k' | 's' | 'm';

export interface Tok {
  /** Syntax class; omit for plain (default-colored) text. */
  c?: TokClass;
  t: string;
}

export type CodeLine = Tok[];

/** Keyword token (orange). */
export const k = (t: string): Tok => ({ c: 'k', t });
/** Symbol/string token (green). */
export const s = (t: string): Tok => ({ c: 's', t });
/** Muted token (dimmed). */
export const m = (t: string): Tok => ({ c: 'm', t });
/** Plain token. */
export const p = (t: string): Tok => ({ t });
/** Plain token of `n` non-breaking spaces — indentation that survives even where
 *  `white-space: pre` is absent (e.g. the `.code-mini` cards), since NBSP does
 *  not collapse in normal HTML flow the way ASCII spaces do. */
export const nb = (n: number): Tok => ({ t: '\u00A0'.repeat(n) });
