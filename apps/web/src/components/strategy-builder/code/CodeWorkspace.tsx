import { readForms } from '@llamatrade/core/strategy/forms';
import type { ValidationIssue } from '@llamatrade/core/strategy/validator';
import { ChevronRight, Code2 } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';

import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import { CodeEditor } from '../CodeEditor';
import type { CodeProblem } from '../codemirror/problemModel';
import type { EngineCheck } from '../hooks/useEngineCheck';
import { KeyValue, RailPanel } from '../rail/RailPanel';

import { cursorInfo, fileName, keywordRows } from './cursorInfo';
import { EngineState } from './EngineState';

interface CodeWorkspaceProps {
  engine: EngineCheck;
  problems: readonly CodeProblem[];
  warnings: readonly ValidationIssue[];
}

interface Cursor {
  offset: number;
  line: number;
  column: number;
}

const Kw = ({ children }: { children: string }) => (
  <span className="font-mono text-[12px] text-fg">{children}</span>
);

/** The code view: the editor with where the cursor sits, and what each form accepts. */
export function CodeWorkspace({ engine, problems, warnings }: CodeWorkspaceProps) {
  const dslCode = useStrategyBuilderStoreWithContext((s) => s.dslCode);
  const strategyName = useStrategyBuilderStoreWithContext((s) => s.strategyName);
  const [cursor, setCursor] = useState<Cursor>({ offset: 0, line: 1, column: 1 });
  const onCursor = useCallback(
    (offset: number, line: number, column: number) => setCursor({ offset, line, column }),
    []
  );

  const forms = useMemo(() => readForms(dslCode), [dslCode]);
  const info = useMemo(
    () => cursorInfo(dslCode, forms, Math.min(cursor.offset, dslCode.length)),
    [dslCode, forms, cursor.offset]
  );
  const rows = useMemo(() => keywordRows(), []);
  const lineCount = dslCode === '' ? 0 : dslCode.split('\n').length;

  return (
    <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_330px] lg:gap-9">
      <section className="panel min-w-0 overflow-hidden">
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <span className="flex min-w-0 items-center gap-2">
            <Code2 className="h-4 w-4 flex-none text-fg-3" aria-hidden="true" />
            <b className="truncate font-mono text-[12.5px] font-medium text-fg-2">
              {fileName(strategyName)}
            </b>
          </span>
          <EngineState engine={engine} warnings={warnings} />
        </header>
        <div className="flex min-h-[37px] flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-line px-4 py-2 font-mono text-[12px] text-fg-3">
          <nav aria-label="Where the cursor sits" className="flex flex-wrap items-center gap-1">
            {info.crumbs.length === 0 ? (
              <span>Outside any form</span>
            ) : (
              info.crumbs.map((c, i) => (
                <span key={i} className="flex items-center gap-1">
                  {i > 0 && <ChevronRight className="h-3 w-3" aria-hidden="true" />}
                  <span className={i === info.crumbs.length - 1 ? 'text-fg' : ''}>{c}</span>
                </span>
              ))
            )}
          </nav>
          {info.accepts.length > 0 && <span>accepts {info.accepts.join(' ')}</span>}
        </div>
        <CodeEditor problems={problems} onCursor={onCursor} />
        <footer className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t border-line px-4 py-2 font-mono text-[11.5px] text-fg-3">
          <span>
            Line {cursor.line}, column {cursor.column} · {lineCount}{' '}
            {lineCount === 1 ? 'line' : 'lines'}
          </span>
          <span className="hidden gap-4 sm:flex">
            <span>Tab accept</span>
            <span>Ctrl Space all options</span>
          </span>
        </footer>
      </section>

      <div className="grid gap-4 lg:sticky lg:top-[72px]">
        <RailPanel title="At the cursor">
          {info.form ? (
            <>
              <p className="m-0 text-[12.5px] leading-relaxed text-fg-2">
                A <b className="font-semibold text-fg">{info.form.head}</b>{' '}
                {info.form.head === 'strategy' ? 'form' : 'block'} {info.place}. {info.role}
              </p>
              <div>
                {info.accepts.length > 0 && (
                  <>
                    <KeyValue
                      k="Set here"
                      v={
                        info.set.length ? (
                          <Kw>{info.set.map((k) => `:${k.name} ${k.value}`.trim()).join(' · ')}</Kw>
                        ) : (
                          'Nothing yet'
                        )
                      }
                    />
                    <KeyValue
                      k="Still to set"
                      v={info.missing.length ? <Kw>{info.missing.join(' ')}</Kw> : 'Nothing'}
                    />
                  </>
                )}
                <KeyValue k="Children" v={<span className="num">{info.children}</span>} />
              </div>
            </>
          ) : (
            <p className="m-0 text-[12.5px] text-fg-2">
              Place the cursor inside a form to see what it is and what it accepts.
            </p>
          )}
        </RailPanel>

        <RailPanel title="Keywords by form">
          <div>
            {rows.map((r) => (
              <KeyValue key={r.forms} k={r.forms} v={<Kw>{r.keywords}</Kw>} />
            ))}
          </div>
        </RailPanel>
        <p className="m-0 px-1 text-[12px] leading-[1.55] text-fg-3">
          The list follows the parser’s own vocabulary, so a keyword that isn’t offered here would
          fail to parse.
        </p>

        {warnings.length > 0 && (
          <section className="rounded-panel bg-sunk px-4 py-3 text-[12.5px] leading-[1.6] text-fg-2">
            <span className="kicker mb-1.5 block">How saving works</span>
            <b className="font-semibold text-fg">Errors</b> stop a strategy from running, so Save
            stays off until they’re fixed. <b className="font-semibold text-fg">Warnings</b> flag
            something that may not be what you meant. You can save with them after a look.
          </section>
        )}
      </div>
    </div>
  );
}
