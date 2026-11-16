import { useEffect, useRef, useState } from 'react';

import { checkDraft } from '../../../services/strategy';
import type { EngineError } from '../codemirror/problemModel';

export type EngineStatus = 'idle' | 'checking' | 'ok' | 'problems' | 'unavailable';

export interface EngineCheck {
  status: EngineStatus;
  /** Errors for `checked`, or null before the first answer. */
  errors: EngineError[] | null;
  /** The text the errors describe. */
  checked: string;
}

const DEBOUNCE_MS = 700;

/** Runs the engine's validation on the draft text after typing pauses; stale answers are dropped. */
export function useEngineCheck(dsl: string, enabled = true): EngineCheck {
  const [state, setState] = useState<EngineCheck>({ status: 'idle', errors: null, checked: '' });
  const seq = useRef(0);

  useEffect(() => {
    if (!enabled || !dsl.trim()) {
      setState({ status: 'idle', errors: null, checked: '' });
      return;
    }
    const id = ++seq.current;
    setState((s) => ({ ...s, status: 'checking' }));
    const timer = setTimeout(() => {
      checkDraft(dsl)
        .then((result) => {
          if (id !== seq.current) return;
          const errors = (result?.errors ?? []).map((e) => ({
            line: e.line,
            column: e.column,
            message: e.message,
          }));
          setState({ status: errors.length ? 'problems' : 'ok', errors, checked: dsl });
        })
        .catch(() => {
          if (id !== seq.current) return;
          setState({ status: 'unavailable', errors: null, checked: dsl });
        });
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [dsl, enabled]);

  return state;
}
