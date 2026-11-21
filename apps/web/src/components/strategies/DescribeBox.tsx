import { useEffect, useRef, useState, type FormEvent } from 'react';

import { CopilotMark } from '../common/Logo';

interface DescribeBoxProps {
  onSubmit: (text: string) => void;
  placeholder: string;
  autoFocus?: boolean;
  busy?: boolean;
}

/** A one-line description for Copilot to draft from. */
export function DescribeBox({ onSubmit, placeholder, autoFocus, busy }: DescribeBoxProps) {
  const [text, setText] = useState('');
  const input = useRef<HTMLInputElement>(null);
  // A frame later, so a surrounding dialog's own focus handling has already run.
  useEffect(() => {
    if (!autoFocus) return;
    const frame = requestAnimationFrame(() => input.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [autoFocus]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (t && !busy) onSubmit(t);
  };
  return (
    <form
      onSubmit={submit}
      className="flex h-11 items-center gap-2 rounded-[6px] border border-line-strong bg-panel pl-3 pr-1.5 focus-within:border-accent focus-within:shadow-[0_0_0_3px_var(--accent-soft)]"
    >
      <CopilotMark className="h-4 w-4 text-fg-3" />
      <label className="sr-only" htmlFor="describe-strategy">
        Describe a strategy
      </label>
      <input
        id="describe-strategy"
        ref={input}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={placeholder}
        className="min-w-0 flex-1 bg-transparent text-[13.5px] text-fg outline-none placeholder:text-fg-3"
      />
      <button type="submit" disabled={!text.trim() || busy} className="btn btn-primary btn-sm">
        Draft it
      </button>
    </form>
  );
}
