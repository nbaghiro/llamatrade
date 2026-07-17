/** Collapsible reasoning block: the Copilot's curated <thinking> for a turn.
 *  Auto-collapses once the answer starts (driven by `autoExpanded`), and stays
 *  expandable afterward. Renders nothing when there is no reasoning. */

import { Brain, ChevronDown, ChevronRight } from 'lucide-react';
import { useState } from 'react';

interface ThinkingBlockProps {
  content: string;
  /** Expanded state when the user hasn't manually toggled (parent-driven auto-collapse). */
  autoExpanded: boolean;
  /** True while the reasoning is still streaming (shows a live pulse). */
  streaming?: boolean;
}

export function ThinkingBlock({ content, autoExpanded, streaming = false }: ThinkingBlockProps) {
  const [override, setOverride] = useState<boolean | null>(null);

  if (!content.trim()) return null;

  const expanded = override ?? autoExpanded;

  return (
    <div className="max-w-full border-2 border-dashed border-ink/25 bg-bone/40">
      <button
        type="button"
        onClick={() => setOverride(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-bone"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 flex-none text-ink/40" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 flex-none text-ink/40" />
        )}
        <Brain className="h-3.5 w-3.5 flex-none text-orange-500" />
        <span className="font-mono text-[9.5px] font-bold uppercase tracking-[0.1em] text-ink/45">
          {streaming && override === null ? 'Thinking…' : 'Thinking'}
        </span>
        {streaming && (
          <span className="ml-0.5 h-1.5 w-1.5 flex-none animate-pulse rounded-full bg-orange-500" />
        )}
      </button>

      {expanded && (
        <div className="whitespace-pre-wrap border-t-2 border-dashed border-ink/15 px-3 py-2 text-xs italic leading-relaxed text-ink/55">
          {content.trim()}
          {streaming && (
            <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-orange-500 align-[-1px]" />
          )}
        </div>
      )}
    </div>
  );
}
