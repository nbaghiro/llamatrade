// CodeMirror theme for the strategy DSL editor
// Provides dark and light themes matching the app design

import { HighlightStyle, syntaxHighlighting } from '@codemirror/language';
import { EditorView } from '@codemirror/view';
import { tags } from '@lezer/highlight';

// Light theme colors - transparent background to show dotted grid
const lightTheme = EditorView.theme({
  '&': {
    color: '#1f2937',
    backgroundColor: 'transparent',
    fontSize: '14px',
    fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
  },
  '.cm-scroller': {
    overflow: 'auto',
  },
  '.cm-content': {
    caretColor: '#3b82f6',
    padding: '16px 0',
  },
  '.cm-cursor, .cm-dropCursor': {
    borderLeftColor: '#3b82f6',
    borderLeftWidth: '2px',
  },
  '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': {
    backgroundColor: 'rgba(59, 130, 246, 0.2)',
  },
  '.cm-gutters': {
    backgroundColor: 'transparent',
    color: '#9ca3af',
    border: 'none',
  },
  '.cm-foldPlaceholder': {
    backgroundColor: 'rgba(0, 0, 0, 0.1)',
    border: 'none',
    color: '#6b7280',
    padding: '0 4px',
    borderRadius: '4px',
  },
  '.cm-tooltip': {
    backgroundColor: '#ffffff',
    border: '1px solid #e5e7eb',
    borderRadius: '8px',
    boxShadow: '0 4px 12px -2px rgb(0 0 0 / 0.15)',
  },
  '.cm-tooltip-autocomplete': {
    '& > ul': {
      fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
    },
    '& > ul > li[aria-selected]': {
      backgroundColor: '#eff6ff',
      color: '#1f2937',
    },
  },
  '.cm-matchingBracket': {
    backgroundColor: 'rgba(59, 130, 246, 0.2)',
    outline: '1px solid rgba(59, 130, 246, 0.5)',
    borderRadius: '2px',
  },
  '.cm-nonmatchingBracket': {
    backgroundColor: 'rgba(239, 68, 68, 0.2)',
    outline: '1px solid rgba(239, 68, 68, 0.5)',
  },
  '.cm-panels': {
    backgroundColor: 'rgba(249, 250, 251, 0.9)',
    borderTop: '1px solid #e5e7eb',
  },
  '.cm-searchMatch': {
    backgroundColor: 'rgba(250, 204, 21, 0.4)',
    borderRadius: '2px',
  },
  '.cm-searchMatch.cm-searchMatch-selected': {
    backgroundColor: 'rgba(250, 204, 21, 0.6)',
  },
  '.cm-line': {
    padding: '0 16px',
  },
}, { dark: false });

// Dark theme colors - transparent background to show dotted grid
const darkTheme = EditorView.theme({
  '&': {
    color: '#e5e7eb',
    backgroundColor: 'transparent',
    fontSize: '14px',
    fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
  },
  '.cm-scroller': {
    overflow: 'auto',
  },
  '.cm-content': {
    caretColor: '#60a5fa',
    padding: '16px 0',
  },
  '.cm-cursor, .cm-dropCursor': {
    borderLeftColor: '#60a5fa',
    borderLeftWidth: '2px',
  },
  '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': {
    backgroundColor: 'rgba(96, 165, 250, 0.25)',
  },
  '.cm-gutters': {
    backgroundColor: 'transparent',
    color: '#6b7280',
    border: 'none',
  },
  '.cm-foldPlaceholder': {
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    border: 'none',
    color: '#9ca3af',
    padding: '0 4px',
    borderRadius: '4px',
  },
  '.cm-tooltip': {
    backgroundColor: '#1f2937',
    border: '1px solid #374151',
    borderRadius: '8px',
    boxShadow: '0 4px 12px -2px rgb(0 0 0 / 0.4)',
  },
  '.cm-tooltip-autocomplete': {
    '& > ul': {
      fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
    },
    '& > ul > li[aria-selected]': {
      backgroundColor: 'rgba(96, 165, 250, 0.2)',
      color: '#e5e7eb',
    },
  },
  '.cm-matchingBracket': {
    backgroundColor: 'rgba(96, 165, 250, 0.25)',
    outline: '1px solid rgba(96, 165, 250, 0.5)',
    borderRadius: '2px',
  },
  '.cm-nonmatchingBracket': {
    backgroundColor: 'rgba(239, 68, 68, 0.25)',
    outline: '1px solid rgba(239, 68, 68, 0.5)',
  },
  '.cm-panels': {
    backgroundColor: 'rgba(15, 23, 42, 0.9)',
    borderTop: '1px solid #374151',
  },
  '.cm-searchMatch': {
    backgroundColor: 'rgba(250, 204, 21, 0.3)',
    borderRadius: '2px',
  },
  '.cm-searchMatch.cm-searchMatch-selected': {
    backgroundColor: 'rgba(250, 204, 21, 0.5)',
  },
  '.cm-line': {
    padding: '0 16px',
  },
}, { dark: true });

// Light syntax highlighting
const lightHighlightStyle = HighlightStyle.define([
  // Keywords: strategy, weight, asset, group, if, else, filter
  { tag: tags.keyword, color: '#2563eb' },
  // Parameters: :method, :weight, :rebalance
  { tag: tags.definitionKeyword, color: '#7c3aed' },
  // Methods: specified, equal, momentum
  { tag: tags.typeName, color: '#059669' },
  // Indicators: sma, ema, rsi
  { tag: tags.variableName, color: '#0891b2' },
  { tag: [tags.special(tags.variableName)], color: '#0891b2', fontWeight: 'bold' },
  // Operators: >, <, cross-above
  { tag: tags.operator, color: '#dc2626' },
  { tag: tags.logicOperator, color: '#dc2626' },
  // Strings: "Strategy Name"
  { tag: tags.string, color: '#ea580c' },
  // Numbers: 50, 0.05
  { tag: tags.number, color: '#ca8a04' },
  // Comments: ; comment
  { tag: tags.comment, color: '#6b7280', fontStyle: 'italic' },
  // Symbols: SPY, VTI (atoms)
  { tag: tags.atom, color: '#1f2937', fontWeight: '600' },
  // Brackets
  { tag: [tags.bracket, tags.paren, tags.squareBracket, tags.brace], color: '#6b7280' },
]);

// Dark syntax highlighting
const darkHighlightStyle = HighlightStyle.define([
  // Keywords: strategy, weight, asset, group, if, else, filter
  { tag: tags.keyword, color: '#60a5fa' },
  // Parameters: :method, :weight, :rebalance
  { tag: tags.definitionKeyword, color: '#a78bfa' },
  // Methods: specified, equal, momentum
  { tag: tags.typeName, color: '#34d399' },
  // Indicators: sma, ema, rsi
  { tag: tags.variableName, color: '#22d3ee' },
  { tag: [tags.special(tags.variableName)], color: '#22d3ee', fontWeight: 'bold' },
  // Operators: >, <, cross-above
  { tag: tags.operator, color: '#f87171' },
  { tag: tags.logicOperator, color: '#f87171' },
  // Strings: "Strategy Name"
  { tag: tags.string, color: '#fb923c' },
  // Numbers: 50, 0.05
  { tag: tags.number, color: '#facc15' },
  // Comments: ; comment
  { tag: tags.comment, color: '#6b7280', fontStyle: 'italic' },
  // Symbols: SPY, VTI (atoms)
  { tag: tags.atom, color: '#f3f4f6', fontWeight: '600' },
  // Brackets
  { tag: [tags.bracket, tags.paren, tags.squareBracket, tags.brace], color: '#9ca3af' },
]);

/**
 * Get the CodeMirror theme extensions for the given color scheme
 */
export function getEditorTheme(isDark: boolean) {
  if (isDark) {
    return [darkTheme, syntaxHighlighting(darkHighlightStyle)];
  }
  return [lightTheme, syntaxHighlighting(lightHighlightStyle)];
}

export { lightTheme, darkTheme, lightHighlightStyle, darkHighlightStyle };
