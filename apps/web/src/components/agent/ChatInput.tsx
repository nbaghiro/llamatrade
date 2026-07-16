/** Copilot composer input box; Enter sends, Shift+Enter inserts a newline. */

import { ArrowRight, Loader2 } from 'lucide-react';
import { KeyboardEvent, useRef, useState } from 'react';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
  /** Prefill the input on mount (e.g. a prompt seeded from the New Strategy console). */
  initialValue?: string;
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = 'Ask Copilot to build, edit, or explain a strategy',
  initialValue = '',
}: ChatInputProps) {
  const [value, setValue] = useState(initialValue);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (trimmed && !disabled) {
      onSend(trimmed);
      setValue('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInput = () => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
    }
  };

  return (
    <div className="flex items-end gap-3 border-2 border-ink bg-paper px-4 py-3 shadow-[4px_4px_0_rgb(var(--lt-ink))]">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          handleInput();
        }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        autoFocus={Boolean(initialValue)}
        rows={1}
        className="flex-1 resize-none bg-transparent text-sm text-ink placeholder-ink/40 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
        style={{ minHeight: '44px', maxHeight: '160px' }}
      />
      <button
        onClick={handleSubmit}
        disabled={disabled || !value.trim()}
        className="flex-shrink-0 grid h-11 w-11 place-items-center border-2 border-ink bg-orange-500 text-ink shadow-[3px_3px_0_rgb(var(--lt-ink))] transition-all hover:bg-orange-600 disabled:opacity-40 disabled:shadow-none"
        title="Send message"
      >
        {disabled ? <Loader2 className="h-5 w-5 animate-spin" /> : <ArrowRight className="h-5 w-5" />}
      </button>
    </div>
  );
}
