// CodeMirror-based code editor for the strategy DSL

import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
import { bracketMatching, foldGutter, indentOnInput } from '@codemirror/language';
import { searchKeymap, highlightSelectionMatches } from '@codemirror/search';
import { EditorState, Compartment } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { AlertCircle } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { useStrategyBuilderStore } from '../../store/strategy-builder';

import { sExprDSL, getEditorTheme, dslAutocomplete, dslLinter } from './codemirror';

export function CodeEditor() {
  const editorRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const themeCompartmentRef = useRef<Compartment | null>(null);
  const isInitializedRef = useRef(false);
  const { dslCode, dslParseError, updateDSLCode, clearDSLParseError } = useStrategyBuilderStore();

  // Detect dark mode
  const [isDark, setIsDark] = useState(() =>
    document.documentElement.classList.contains('dark')
  );

  // Watch for theme changes
  useEffect(() => {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.attributeName === 'class') {
          setIsDark(document.documentElement.classList.contains('dark'));
        }
      });
    });

    observer.observe(document.documentElement, { attributes: true });
    return () => observer.disconnect();
  }, []);

  // Handle code changes from the editor
  const handleChange = useCallback((value: string) => {
    // Skip updates during initialization
    if (!isInitializedRef.current) return;
    updateDSLCode(value);
  }, [updateDSLCode]);

  // Reconfigure theme when it changes
  useEffect(() => {
    if (viewRef.current && themeCompartmentRef.current) {
      viewRef.current.dispatch({
        effects: themeCompartmentRef.current.reconfigure(getEditorTheme(isDark)),
      });
    }
  }, [isDark]);

  // Initialize the editor
  useEffect(() => {
    if (!editorRef.current || viewRef.current) return;

    // Create compartment for this instance
    const themeCompartment = new Compartment();
    themeCompartmentRef.current = themeCompartment;

    // Create new editor
    const state = EditorState.create({
      doc: dslCode,
      extensions: [
        foldGutter(),
        bracketMatching(),
        indentOnInput(),
        highlightSelectionMatches(),
        history(),
        keymap.of([
          ...defaultKeymap,
          ...historyKeymap,
          ...searchKeymap,
        ]),
        sExprDSL(),
        dslAutocomplete,
        dslLinter,
        themeCompartment.of(getEditorTheme(isDark)),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            handleChange(update.state.doc.toString());
          }
        }),
      ],
    });

    const view = new EditorView({
      state,
      parent: editorRef.current,
    });

    viewRef.current = view;

    // Mark as initialized after a tick to skip initial events
    requestAnimationFrame(() => {
      isInitializedRef.current = true;
    });

    return () => {
      view.destroy();
      viewRef.current = null;
      themeCompartmentRef.current = null;
      isInitializedRef.current = false;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run once on mount

  // Update editor content when dslCode changes externally (e.g., when switching from tree view)
  useEffect(() => {
    if (viewRef.current) {
      const currentContent = viewRef.current.state.doc.toString();
      if (currentContent !== dslCode) {
        viewRef.current.dispatch({
          changes: {
            from: 0,
            to: currentContent.length,
            insert: dslCode,
          },
        });
      }
    }
  }, [dslCode]);

  return (
    <div className="flex flex-col h-full">
      {/* Error banner */}
      {dslParseError && (
        <div className="flex items-center gap-2 mx-4 mt-2 px-3 py-2 bg-red-100/80 dark:bg-red-900/40 rounded-lg border border-red-200 dark:border-red-800/50">
          <AlertCircle size={14} className="text-red-600 dark:text-red-400 flex-shrink-0" />
          <span className="text-sm text-red-700 dark:text-red-300 flex-1">{dslParseError}</span>
          <button
            onClick={clearDSLParseError}
            className="text-xs text-red-600 dark:text-red-400 hover:underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Editor container - transparent to show dotted grid */}
      <div
        ref={editorRef}
        className="flex-1 overflow-auto"
      />
    </div>
  );
}
