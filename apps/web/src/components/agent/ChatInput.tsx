import { ArrowUp } from 'lucide-react';
import { useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  /** True while a reply streams; the composer stays editable but won't send. */
  busy?: boolean;
  placeholder?: string;
  /** Prefills the input on mount. Remount with a new key to replace it. */
  initialValue?: string;
}

const MAX_HEIGHT = 160;

/** Copilot's composer. Enter sends, Shift+Enter starts a new line. */
export function ChatInput({
  onSend,
  disabled = false,
  busy = false,
  placeholder = 'Ask Copilot to build, edit or explain a strategy',
  initialValue = '',
}: ChatInputProps) {
  const [value, setValue] = useState(initialValue);
  const ref = useRef<HTMLTextAreaElement>(null);
  const canSend = !disabled && !busy && value.trim().length > 0;

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  useLayoutEffect(() => {
    const el = ref.current;
    if (el && initialValue) {
      el.focus();
      el.setSelectionRange(initialValue.length, initialValue.length);
    }
  }, [initialValue]);

  const submit = () => {
    if (!canSend) return;
    onSend(value.trim());
    setValue('');
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div
      className={`flex items-end gap-2 rounded-[12px] border border-line-strong bg-panel py-2 pl-3.5 pr-2 focus-within:border-accent ${
        disabled ? 'opacity-60' : ''
      }`}
    >
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        rows={1}
        aria-label="Message Copilot"
        className="min-h-[32px] flex-1 resize-none bg-transparent py-1.5 text-[14px] leading-5 text-fg outline-none placeholder:text-fg-3 disabled:cursor-not-allowed"
        style={{ maxHeight: MAX_HEIGHT }}
      />
      <button
        type="button"
        onClick={submit}
        disabled={!canSend}
        aria-label="Send"
        className="grid h-8 w-8 flex-none place-items-center rounded-full bg-fg text-canvas transition-opacity disabled:opacity-40"
      >
        <ArrowUp className="h-4 w-4" strokeWidth={2} />
      </button>
    </div>
  );
}
