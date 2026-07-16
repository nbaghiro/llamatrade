/** Copilot response-in-progress row: ✦ mark + streaming text or typing dots. */

import { Sparkles } from 'lucide-react';

interface StreamingIndicatorProps {
  content?: string;
}

export function StreamingIndicator({ content }: StreamingIndicatorProps) {
  return (
    <div className="flex gap-3.5">
      <div className="grid h-9 w-9 flex-none place-items-center border-2 border-ink bg-ink">
        <Sparkles className="h-4 w-4 text-orange-500" />
      </div>

      <div className="max-w-[80%] border-2 border-ink bg-paper px-4 py-3 shadow-[4px_4px_0_rgb(var(--lt-ink))]">
        {content ? (
          <div className="whitespace-pre-wrap text-sm text-ink">
            {content}
            <span className="ml-0.5 inline-block h-4 w-2 animate-pulse bg-orange-500 align-[-2px]" />
          </div>
        ) : (
          <div className="flex items-center gap-1 py-1">
            <span className="h-2 w-2 animate-bounce bg-orange-500" style={{ animationDelay: '0ms' }} />
            <span className="h-2 w-2 animate-bounce bg-orange-500" style={{ animationDelay: '150ms' }} />
            <span className="h-2 w-2 animate-bounce bg-orange-500" style={{ animationDelay: '300ms' }} />
          </div>
        )}
      </div>
    </div>
  );
}
