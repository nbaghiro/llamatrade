import { ChevronRight } from 'lucide-react';
import { useState } from 'react';

interface ThinkingBlockProps {
  content: string;
  /** Open state until the user toggles it; the parent closes it once the answer starts. */
  autoExpanded: boolean;
  streaming?: boolean;
}

/** Copilot's reasoning for a turn, folded under a small toggle. */
export function ThinkingBlock({ content, autoExpanded, streaming = false }: ThinkingBlockProps) {
  const [override, setOverride] = useState<boolean | null>(null);
  if (!content.trim()) return null;
  const expanded = override ?? autoExpanded;

  return (
    <div className="max-w-full">
      <button
        type="button"
        onClick={() => setOverride(!expanded)}
        aria-expanded={expanded}
        className="inline-flex items-center gap-1 text-[12.5px] text-fg-3 hover:text-fg-2"
      >
        <ChevronRight
          className={`h-3.5 w-3.5 transition-transform ${expanded ? 'rotate-90' : ''}`}
        />
        {streaming && override === null ? 'Thinking…' : 'Reasoning'}
      </button>
      {expanded && (
        <div className="mt-1.5 whitespace-pre-wrap border-l-2 border-line pl-3 text-[12.5px] leading-relaxed text-fg-3">
          {content.trim()}
        </div>
      )}
    </div>
  );
}
