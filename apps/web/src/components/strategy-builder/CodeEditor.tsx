// The strategy language editor, with the engine's problems drawn under their line.

import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
import { bracketMatching, foldGutter, indentOnInput } from '@codemirror/language';
import { highlightSelectionMatches, searchKeymap } from '@codemirror/search';
import { Compartment, EditorState } from '@codemirror/state';
import { EditorView, keymap, lineNumbers } from '@codemirror/view';
import { useCallback, useEffect, useRef } from 'react';

import { useStrategyBuilderStoreWithContext } from '../../store/strategy-builder';

import {
  dslAutocomplete,
  dslLinter,
  getEditorTheme,
  problemsField,
  problemsTheme,
  setProblems,
  sExprDSL,
} from './codemirror';
import type { CodeProblem } from './codemirror/problemModel';

interface CodeEditorProps {
  readOnly?: boolean;
  /** Engine problems for the current text; ignored while the text differs from what was checked. */
  problems?: readonly CodeProblem[];
}

export function CodeEditor({ readOnly = false, problems = [] }: CodeEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const readOnlyCompartment = useRef(new Compartment());
  const isInitializedRef = useRef(false);
  // True while pushing a store-driven update into the editor, so the echo isn't treated as typing.
  const isApplyingExternalRef = useRef(false);
  const { dslCode, dslParseError, updateDSLCode, clearDSLParseError } =
    useStrategyBuilderStoreWithContext();

  const handleChange = useCallback(
    (value: string) => {
      if (!isInitializedRef.current || isApplyingExternalRef.current) return;
      updateDSLCode(value);
    },
    [updateDSLCode]
  );
  const changeRef = useRef(handleChange);
  changeRef.current = handleChange;

  useEffect(() => {
    if (!editorRef.current || viewRef.current) return;
    const view = new EditorView({
      state: EditorState.create({
        doc: dslCode,
        extensions: [
          lineNumbers(),
          foldGutter(),
          bracketMatching(),
          indentOnInput(),
          highlightSelectionMatches(),
          history(),
          keymap.of([...defaultKeymap, ...historyKeymap, ...searchKeymap]),
          sExprDSL(),
          dslAutocomplete,
          dslLinter,
          problemsField,
          problemsTheme,
          ...getEditorTheme(),
          EditorView.lineWrapping,
          readOnlyCompartment.current.of(EditorState.readOnly.of(readOnly)),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) changeRef.current(update.state.doc.toString());
          }),
        ],
      }),
      parent: editorRef.current,
    });
    viewRef.current = view;
    const raf = requestAnimationFrame(() => {
      isInitializedRef.current = true;
    });
    return () => {
      cancelAnimationFrame(raf);
      view.destroy();
      viewRef.current = null;
      isInitializedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: readOnlyCompartment.current.reconfigure(EditorState.readOnly.of(readOnly)),
    });
  }, [readOnly]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current !== dslCode) {
      isApplyingExternalRef.current = true;
      view.dispatch({ changes: { from: 0, to: current.length, insert: dslCode } });
      isApplyingExternalRef.current = false;
    }
  }, [dslCode]);

  useEffect(() => {
    viewRef.current?.dispatch({ effects: setProblems.of(problems) });
  }, [problems]);

  return (
    <div className="flex min-h-0 flex-col">
      {dslParseError && (
        <div
          role="alert"
          className="mx-4 mb-2 mt-3 flex items-center gap-3 rounded-[6px] border border-risk-line bg-risk-soft px-3 py-2 text-[12.5px]"
        >
          <span className="flex-1 text-fg">
            <b className="font-semibold text-risk">The outline can’t follow this yet.</b>{' '}
            {dslParseError}
          </span>
          <button type="button" onClick={clearDSLParseError} className="btn btn-ghost btn-sm">
            Dismiss
          </button>
        </div>
      )}
      <div ref={editorRef} className="min-h-[420px] flex-1 overflow-auto" />
    </div>
  );
}
