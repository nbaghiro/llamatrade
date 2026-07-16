// CodeMirror DSL theme: a Monolith dark terminal (matches marketing/auth snippets), intentionally dark inside the light app.

import { HighlightStyle, syntaxHighlighting } from '@codemirror/language';
import { EditorView } from '@codemirror/view';
import { tags } from '@lezer/highlight';

const MONO_FONT = '"Space Mono", ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace';

// Monolith terminal palette (from the marketing snippet: --orange keywords,
// #3ddc6b symbols, #8ea79b :params, bone-dim parens).
const INK = '#0d0d0d';
const BONE = 'rgb(var(--lt-bone))';
const ORANGE = '#ff4d1c';
const SYM = '#3ddc6b'; // tickers + strings
const PARAM = '#8ea79b'; // :params (sage)
const NUM = '#6ea8ff'; // numbers (readable blue on ink)
const boneA = (a: number) => `rgb(var(--lt-bone) / ${a})`;

const terminalTheme = EditorView.theme(
  {
    '&': {
      color: BONE,
      backgroundColor: INK,
      fontSize: '14px',
      fontFamily: MONO_FONT,
    },
    '.cm-scroller': { overflow: 'auto', fontFamily: MONO_FONT },
    '.cm-content': { caretColor: ORANGE, padding: '16px 0' },
    '.cm-cursor, .cm-dropCursor': { borderLeftColor: ORANGE, borderLeftWidth: '2px' },
    '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': {
      backgroundColor: 'rgba(255, 77, 28, 0.28)',
    },
    '.cm-activeLine': { backgroundColor: boneA(0.05) },
    '.cm-activeLineGutter': { backgroundColor: boneA(0.07) },
    '.cm-gutters': {
      backgroundColor: INK,
      color: boneA(0.32),
      border: 'none',
      borderRight: `2px solid ${boneA(0.16)}`,
    },
    '.cm-foldPlaceholder': {
      backgroundColor: boneA(0.12),
      border: 'none',
      color: BONE,
      padding: '0 4px',
      borderRadius: '0',
    },
    '.cm-tooltip': {
      backgroundColor: '#141414',
      border: `2px solid ${boneA(0.35)}`,
      borderRadius: '0',
      boxShadow: `4px 4px 0 ${ORANGE}`,
      color: BONE,
    },
    '.cm-tooltip-autocomplete': {
      '& > ul': { fontFamily: MONO_FONT },
      '& > ul > li': { color: BONE },
      '& > ul > li[aria-selected]': { backgroundColor: ORANGE, color: INK },
    },
    '.cm-matchingBracket': {
      backgroundColor: 'rgba(255, 77, 28, 0.22)',
      outline: `1px solid ${boneA(0.5)}`,
      borderRadius: '0',
    },
    '.cm-nonmatchingBracket': {
      backgroundColor: 'rgba(200, 30, 30, 0.3)',
      outline: '1px solid rgba(200, 30, 30, 0.6)',
    },
    '.cm-panels': { backgroundColor: INK, borderTop: `2px solid ${boneA(0.16)}`, color: BONE },
    '.cm-searchMatch': { backgroundColor: 'rgba(255, 77, 28, 0.25)', borderRadius: '0' },
    '.cm-searchMatch.cm-searchMatch-selected': { backgroundColor: 'rgba(255, 77, 28, 0.45)' },
    '.cm-line': { padding: '0 16px' },
  },
  { dark: true }
);

// Syntax highlighting — matches the marketing DSL terminal token colors.
const terminalHighlightStyle = HighlightStyle.define([
  // Keywords: strategy, weight, asset, group, if, else, filter → orange
  { tag: tags.keyword, color: ORANGE, fontWeight: 'bold' },
  // `:params` (:method, :weight, :rebalance, :benchmark, :by …) → sage.
  // language.ts tags these as propertyName so they read distinct from keywords.
  { tag: tags.propertyName, color: PARAM },
  { tag: tags.definitionKeyword, color: PARAM },
  // Method/enum values (equal, specified, risk-parity, momentum) → soft bone (plain)
  { tag: tags.typeName, color: boneA(0.8) },
  // Fallback identifiers → bone
  { tag: tags.variableName, color: BONE },
  // Indicators: sma, ema, rsi, price → orange (function-like)
  { tag: [tags.special(tags.variableName)], color: ORANGE, fontWeight: 'bold' },
  // Operators: >, <, cross-above → orange
  { tag: tags.operator, color: ORANGE, fontWeight: 'bold' },
  { tag: tags.logicOperator, color: ORANGE, fontWeight: 'bold' },
  // Strings: "Strategy Name" → green
  { tag: tags.string, color: SYM },
  // Numbers: 50, 0.05 → blue
  { tag: tags.number, color: NUM },
  // Comments: ; comment → dim bone italic
  { tag: tags.comment, color: boneA(0.42), fontStyle: 'italic' },
  // Symbols / tickers: SPY, VTI (atoms) → green
  { tag: tags.atom, color: SYM, fontWeight: '600' },
  // Brackets / parens → dim bone (marketing `.tp`)
  { tag: [tags.bracket, tags.paren, tags.squareBracket, tags.brace], color: boneA(0.4) },
]);

/**
 * Get the CodeMirror theme extensions. The code view is always the Monolith dark
 * terminal (the `isDark` argument is accepted for API compatibility but ignored).
 */
export function getEditorTheme(_isDark?: boolean) {
  return [terminalTheme, syntaxHighlighting(terminalHighlightStyle)];
}

// Back-compat exports (both point at the single terminal theme).
const lightTheme = terminalTheme;
const darkTheme = terminalTheme;
export { lightTheme, darkTheme, terminalTheme, terminalHighlightStyle };
