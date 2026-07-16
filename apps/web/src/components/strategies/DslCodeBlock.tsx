import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { useEffect, useRef } from 'react';

import { getEditorTheme, sExprDSL } from '../strategy-builder/codemirror';

interface DslCodeBlockProps {
  code: string;
  /** Wrapper classes; defaults to the strategies-drawer framing. */
  className?: string;
}

// Bound the viewer to its container: long strategies scroll inside the block
// (both axes) instead of stretching the parent past the panel width.
const sizeLimit = EditorView.theme({
  '&': { maxHeight: '52vh', maxWidth: '100%' },
  '.cm-scroller': { overflow: 'auto', maxWidth: '100%' },
});

// Read-only DSL viewer reusing the builder's grammar + terminal theme; lazy-loaded so CodeMirror stays out of the list bundle.
export default function DslCodeBlock({
  code,
  className = 'mx-4 mb-3.5 border-2 border-ink',
}: DslCodeBlockProps) {
  const parentRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);

  useEffect(() => {
    if (!parentRef.current) return;
    const view = new EditorView({
      state: EditorState.create({
        doc: code,
        extensions: [
          sExprDSL(),
          ...getEditorTheme(),
          sizeLimit,
          EditorState.readOnly.of(true),
          EditorView.editable.of(false),
        ],
      }),
      parent: parentRef.current,
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current !== code) {
      view.dispatch({ changes: { from: 0, to: current.length, insert: code } });
    }
  }, [code]);

  // min-w-0 + overflow-hidden keep the block from being widened by CodeMirror's
  // long lines when it sits in a flex/shrink context (e.g. the copilot card).
  return <div ref={parentRef} className={`min-w-0 overflow-hidden ${className}`} />;
}
