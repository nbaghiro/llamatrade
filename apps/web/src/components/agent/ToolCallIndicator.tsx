/** A single tool-execution row (dotted border) matching the Copilot v1 design. */

import { Settings } from 'lucide-react';

interface ToolCallIndicatorProps {
  toolName: string;
  status: 'running' | 'complete' | 'error';
  /** Short summary of arguments/result shown dim after the function name. */
  detail?: string;
  resultPreview?: string;
  /** Execution time in ms (rendered as "· 0.4s" when complete). */
  durationMs?: number;
}

export function ToolCallIndicator({
  toolName,
  status,
  detail,
  resultPreview,
  durationMs,
}: ToolCallIndicatorProps) {
  const meta = detail || resultPreview;
  const seconds = durationMs && durationMs > 0 ? `${(durationMs / 1000).toFixed(1)}s` : null;

  return (
    <div className="flex items-center gap-2.5 border-2 border-dotted border-ink bg-paper px-3 py-2 font-mono text-xs">
      <Settings className={`h-3.5 w-3.5 text-ink ${status === 'running' ? 'animate-spin' : ''}`} />
      <span className="font-bold text-ink">{toolName}</span>
      {meta && <span className="truncate text-ink/50">{meta}</span>}

      <span
        className={`ml-auto flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide ${
          status === 'error' ? 'text-red-600' : status === 'running' ? 'text-orange-500' : 'text-green-600'
        }`}
      >
        <span
          className={`h-1.5 w-1.5 bg-current ${status === 'running' ? 'animate-pulse' : ''}`}
        />
        {status === 'running' ? 'running…' : status === 'error' ? 'error' : 'done'}
        {status === 'complete' && seconds && <span className="text-ink/50">· {seconds}</span>}
      </span>
    </div>
  );
}
