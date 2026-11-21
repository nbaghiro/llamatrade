import { Fragment, useEffect, useMemo, useRef, useState } from 'react';

import { strategyById } from '../data';

import { results, type Group } from './commands';
import { TurnView } from './copilot';
import { useCopilot } from './copilotContext';
import { Kbd, Mono } from './ui';

const GROUP_LABEL: Record<Group, string> = { Run: 'Run', Jump: 'Jump to', Ask: 'Ask Copilot' };

/** ⌘K or /: one line that jumps, runs commands and asks Copilot, with the thread under it. */
export function CommandBar({
  context,
  showThread,
  onClose,
}: {
  context?: string;
  showThread: boolean;
  onClose: () => void;
}) {
  const { run, turns } = useCopilot();
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const list = useMemo(() => results(q, context), [q, context]);
  const threadMode = showThread && !q.trim() && turns.length > 0;
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => setSel(0), [q]);
  useEffect(() => {
    const el = scroller.current;
    if (el && threadMode) el.scrollTop = el.scrollHeight;
  });

  const exec = (i: number) => {
    const r = list[i];
    if (!r) return;
    setQ('');
    run(r.action);
  };

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute inset-0 h-full w-full cursor-default bg-canvas/70"
      />
      <div className="relative mx-auto max-w-[760px] px-4 pt-[64px]">
        <div
          role="dialog"
          aria-label="Command bar"
          className="animate-rise overflow-hidden rounded-[10px] border bg-canvas"
          style={{
            borderColor: 'color-mix(in srgb, rgb(var(--fg)) 26%, rgb(var(--line)))',
            boxShadow:
              '0 40px 100px -40px color-mix(in srgb, rgb(var(--fg)) 22%, transparent), 0 24px 48px -24px rgb(0 0 0 / 0.45)',
          }}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              exec(sel);
            }}
            className="flex h-12 items-center gap-3 border-b border-line px-4"
          >
            <span className="font-mono text-[15px] text-fg-3" aria-hidden="true">
              ›
            </span>
            <input
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'ArrowDown' || (e.key === 'Tab' && !e.shiftKey)) {
                  e.preventDefault();
                  setSel((s) => Math.min(list.length - 1, s + 1));
                }
                if (e.key === 'ArrowUp' || (e.key === 'Tab' && e.shiftKey)) {
                  e.preventDefault();
                  setSel((s) => Math.max(0, s - 1));
                }
              }}
              placeholder={
                context
                  ? `Ask about ${strategyById(context)?.name ?? 'this'}, or type a command`
                  : 'Type a strategy, a question, or a command like backtest recession radar 5y'
              }
              aria-label="Command or question"
              className="min-w-0 flex-1 bg-transparent font-mono text-[14px] text-fg outline-none placeholder:text-fg-3"
            />
            <Kbd>esc</Kbd>
          </form>
          <div ref={scroller} className="max-h-[min(560px,calc(100vh-180px))] overflow-y-auto">
            {threadMode ? (
              <div className="divide-y divide-line px-4">
                {turns.map((t) => (
                  <TurnView key={t.id} turn={t} onGo={onClose} />
                ))}
              </div>
            ) : (
              <div role="listbox" aria-label="Results" className="py-1">
                {list.map((r, i) => (
                  <Fragment key={r.id}>
                    {(i === 0 || list[i - 1].group !== r.group) && (
                      <div className="flex h-7 items-end px-4 pb-1">
                        <Mono className="text-fg-3">
                          {q.trim() ? GROUP_LABEL[r.group] : i === 0 ? 'Try' : 'Pages'}
                        </Mono>
                      </div>
                    )}
                    <button
                      type="button"
                      role="option"
                      aria-selected={i === sel}
                      onMouseEnter={() => setSel(i)}
                      onClick={() => exec(i)}
                      className={`relative flex h-8 w-full items-center gap-3 px-4 text-left text-[13px] ${
                        i === sel
                          ? 'bg-sunk text-fg before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-fg'
                          : 'text-fg-2'
                      }`}
                    >
                      <span className="w-[14px] flex-none text-center font-mono text-[11px] text-fg-3">
                        {r.group === 'Ask' ? '?' : r.group === 'Run' ? '›' : '→'}
                      </span>
                      <span
                        className={`min-w-0 flex-1 truncate ${r.group === 'Run' ? 'font-mono text-[12.5px]' : ''}`}
                      >
                        {r.label}
                      </span>
                      {r.detail && (
                        <span className="hidden flex-none font-mono text-[11px] text-fg-3 sm:inline">
                          {r.detail}
                        </span>
                      )}
                      {r.key && <Kbd>{r.key}</Kbd>}
                      {i === sel && <Kbd>↵</Kbd>}
                    </button>
                  </Fragment>
                ))}
              </div>
            )}
          </div>
          <div className="flex h-8 items-center gap-4 border-t border-line bg-panel/60 px-4 font-mono text-[10.5px] text-fg-3">
            {threadMode ? (
              <span>Type to ask a follow-up or run a command</span>
            ) : (
              <>
                <span className="inline-flex items-center gap-1.5">
                  <Kbd>↑</Kbd>
                  <Kbd>↓</Kbd> move
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Kbd>↵</Kbd> run
                </span>
              </>
            )}
            <span className="ml-auto">
              {turns.length / 2} {turns.length === 2 ? 'question' : 'questions'} in this thread
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
