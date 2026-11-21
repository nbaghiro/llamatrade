import { ArrowUp, X } from 'lucide-react';
import { useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  /** True while a reply streams; the composer stays editable but won't send. */
  busy?: boolean;
  placeholder?: string;
  /** Prefills the input on mount. Remount with a new key to replace it. */
  initialValue?: string;
  /** Chips under the text, such as the subject the question is about. */
  chips?: ReactNode;
  /** A short line beside the send button. */
  hint?: ReactNode;
  /** The open canvas's taller composer. */
  large?: boolean;
  autoFocus?: boolean;
}

const MAX_HEIGHT = 160;

/** A removable chip naming what the question is about. */
export function SubjectChip({
  icon,
  label,
  onRemove,
}: {
  icon?: ReactNode;
  label: string;
  onRemove?: () => void;
}) {
  return (
    <span className="inline-flex h-7 max-w-full items-center gap-1.5 rounded-full bg-sunk pl-2.5 pr-1.5 text-[12.5px] text-fg">
      {icon}
      <span className="truncate">{label}</span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Stop asking about ${label}`}
          className="grid h-4 w-4 place-items-center rounded-full text-fg-3 hover:text-fg"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </span>
  );
}

/** Copilot's composer. Enter sends, Shift+Enter starts a new line. */
export function ChatInput({
  onSend,
  disabled = false,
  busy = false,
  placeholder = 'Ask Copilot to build, edit or explain a strategy',
  initialValue = '',
  chips,
  hint,
  large = false,
  autoFocus = false,
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
    if (el && (initialValue || autoFocus)) {
      el.focus();
      el.setSelectionRange(initialValue.length, initialValue.length);
    }
  }, [initialValue, autoFocus]);

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
      className={`grid gap-2 rounded-[14px] border border-line bg-panel pb-2.5 transition-[border-color,box-shadow] focus-within:border-line-strong ${
        large
          ? 'px-[18px] pt-4 shadow-[0_18px_50px_-24px_rgb(0_0_0/0.22)]'
          : 'px-4 pt-3 shadow-[0_8px_30px_-18px_rgb(0_0_0/0.2)]'
      } ${disabled ? 'opacity-60' : ''}`}
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
        className={`resize-none bg-transparent leading-6 text-fg outline-none placeholder:text-fg-3 disabled:cursor-not-allowed ${
          large ? 'min-h-[52px] text-[15px]' : 'min-h-[24px] text-[15px]'
        }`}
        style={{ maxHeight: MAX_HEIGHT }}
      />
      <div className="flex min-w-0 items-center gap-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
          {chips}
          {hint && <span className="hidden truncate text-[12px] text-fg-3 sm:inline">{hint}</span>}
        </div>
        <button
          type="button"
          onClick={submit}
          disabled={!canSend}
          aria-label="Send"
          className="grid h-8 w-8 flex-none place-items-center rounded-full bg-fg text-canvas transition-opacity disabled:bg-sunk disabled:text-fg-3"
        >
          <ArrowUp className="h-4 w-4" strokeWidth={2} />
        </button>
      </div>
    </div>
  );
}
