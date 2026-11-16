// CodeMirror theme for the strategy language, drawn from the app's tokens so it follows mode and accent.

import { HighlightStyle, syntaxHighlighting } from '@codemirror/language';
import { EditorView } from '@codemirror/view';
import { tags } from '@lezer/highlight';

const tok = (name: string, alpha?: number) =>
  alpha === undefined ? `rgb(var(--${name}))` : `rgb(var(--${name}) / ${alpha})`;

const MONO = 'var(--font-mono)';

const tokenTheme = EditorView.theme({
  '&': {
    color: tok('fg'),
    backgroundColor: tok('panel'),
    fontSize: '13px',
    fontFamily: MONO,
  },
  '&.cm-focused': { outline: 'none' },
  '.cm-scroller': { overflow: 'auto', fontFamily: MONO, lineHeight: '1.8' },
  '.cm-content': { caretColor: tok('accent'), padding: '12px 0' },
  '.cm-cursor, .cm-dropCursor': { borderLeftColor: tok('accent'), borderLeftWidth: '2px' },
  '.cm-content ::selection, .cm-line ::selection': { backgroundColor: tok('accent', 0.28) },
  '&.cm-focused .cm-selectionBackground, .cm-selectionBackground': {
    backgroundColor: tok('accent', 0.22),
  },
  '.cm-selectionMatch': { backgroundColor: 'var(--accent-soft)' },
  '.cm-activeLine': { backgroundColor: tok('sunk', 0.6) },
  '.cm-activeLineGutter': { backgroundColor: tok('sunk', 0.6) },
  '.cm-gutters': {
    backgroundColor: tok('panel'),
    color: tok('fg-3'),
    border: 'none',
  },
  '.cm-lineNumbers .cm-gutterElement': { padding: '0 14px 0 12px', opacity: '0.75' },
  '.cm-foldPlaceholder': {
    backgroundColor: tok('sunk'),
    border: 'none',
    color: tok('fg-2'),
    padding: '0 4px',
  },
  '.cm-tooltip': {
    backgroundColor: tok('panel'),
    border: `1px solid ${tok('line-strong')}`,
    borderRadius: '8px',
    boxShadow: 'var(--shadow-lg)',
    color: tok('fg'),
  },
  '.cm-tooltip-autocomplete': {
    '& > ul': { fontFamily: MONO },
    '& > ul > li': { color: tok('fg-2') },
    '& > ul > li[aria-selected]': { backgroundColor: 'var(--accent-soft)', color: tok('accent') },
  },
  '.cm-matchingBracket': {
    backgroundColor: tok('sunk'),
    outline: `1px solid ${tok('line-strong')}`,
  },
  '.cm-nonmatchingBracket': {
    backgroundColor: 'var(--risk-soft)',
    outline: '1px solid var(--risk-line)',
  },
  '.cm-panels': {
    backgroundColor: tok('panel'),
    borderTop: `1px solid ${tok('line')}`,
    color: tok('fg'),
  },
  '.cm-searchMatch': { backgroundColor: 'var(--accent-soft)' },
  '.cm-searchMatch.cm-searchMatch-selected': { backgroundColor: tok('accent', 0.3) },
  '.cm-line': { padding: '0 16px' },
  '.cm-lintRange-error': {
    backgroundImage: 'none',
    textDecoration: `underline wavy ${tok('risk')}`,
    textUnderlineOffset: '4px',
  },
  '.cm-lintRange-warning': {
    backgroundImage: 'none',
    textDecoration: `underline dotted ${tok('risk')}`,
    textUnderlineOffset: '4px',
  },
  '.cm-diagnostic-error': { borderLeftColor: tok('risk') },
  '.cm-diagnostic-warning': { borderLeftColor: tok('risk') },
});

const tokenHighlight = HighlightStyle.define([
  { tag: tags.keyword, color: tok('accent') },
  { tag: [tags.propertyName, tags.definitionKeyword], color: tok('fg-2') },
  { tag: tags.typeName, color: tok('fg') },
  { tag: tags.variableName, color: tok('fg') },
  { tag: tags.special(tags.variableName), color: tok('accent') },
  { tag: [tags.operator, tags.logicOperator], color: tok('accent') },
  { tag: tags.string, color: tok('fg-2') },
  { tag: tags.number, color: tok('fg') },
  { tag: tags.comment, color: tok('fg-3'), fontStyle: 'italic' },
  { tag: tags.atom, color: tok('fg'), fontWeight: '600' },
  { tag: [tags.bracket, tags.paren, tags.squareBracket, tags.brace], color: tok('fg-3') },
]);

export function getEditorTheme() {
  return [tokenTheme, syntaxHighlighting(tokenHighlight)];
}
