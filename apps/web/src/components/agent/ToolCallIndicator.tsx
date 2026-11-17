import { AlertTriangle, Check } from 'lucide-react';

interface ToolCallIndicatorProps {
  toolName: string;
  status: 'running' | 'waiting' | 'complete' | 'error';
  /** Short summary of the arguments or result. */
  detail?: string;
  resultPreview?: string;
  durationMs?: number;
}

/** One tool step in the thread, as a quiet pill. */
export function ToolCallIndicator({
  toolName,
  status,
  detail,
  resultPreview,
  durationMs,
}: ToolCallIndicatorProps) {
  const meta =
    status === 'waiting'
      ? 'waiting for your approval below'
      : status === 'error'
        ? 'failed'
        : detail || resultPreview;
  const seconds =
    status === 'complete' && durationMs && durationMs > 0
      ? `${(durationMs / 1000).toFixed(1)} s`
      : null;

  return (
    <div
      className={`inline-flex max-w-full items-center gap-2 justify-self-start rounded-full border px-2.5 py-1 text-[12.5px] ${
        status === 'error' ? 'border-risk-line text-risk' : 'border-line text-fg-3'
      }`}
    >
      {status === 'running' || status === 'waiting' ? (
        <span
          aria-hidden="true"
          className={`h-2 w-2 flex-none rounded-full bg-accent ${status === 'running' ? 'motion-safe:animate-pulse' : ''}`}
        />
      ) : status === 'error' ? (
        <AlertTriangle className="h-3.5 w-3.5 flex-none" />
      ) : (
        <Check className="h-3.5 w-3.5 flex-none" />
      )}
      <b className="flex-none font-mono text-xs font-medium text-fg-2">{toolName}</b>
      {meta && <span className="truncate">{meta}</span>}
      {seconds && <span className="flex-none">· {seconds}</span>}
      <span className="sr-only">
        {status === 'running' ? 'Running' : status === 'complete' ? 'Done' : ''}
      </span>
    </div>
  );
}
