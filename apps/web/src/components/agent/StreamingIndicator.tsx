import { CopilotMark } from '../common/Logo';

import { hideDraftBlock } from './draftQuestions';

interface StreamingIndicatorProps {
  content?: string;
}

/** Copilot's reply while it streams in, with three dots beside the name until it finishes. */
export function StreamingIndicator({ content: raw }: StreamingIndicatorProps) {
  const content = raw ? hideDraftBlock(raw) : raw;
  return (
    <div className="grid gap-2.5 motion-safe:animate-rise" aria-live="polite">
      <span className="flex items-center gap-2 text-[12px] text-fg-3">
        <CopilotMark className="h-3.5 w-3.5 text-fg" />
        Copilot
        <span className="inline-flex gap-[3px]" role="status" aria-label="Copilot is replying">
          {[0, 150, 300].map((delay) => (
            <i
              key={delay}
              aria-hidden="true"
              className="h-[5px] w-[5px] rounded-full bg-fg-3 motion-safe:animate-bob"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
        </span>
      </span>
      {content && (
        <div className="whitespace-pre-wrap text-[15px] leading-[1.65] text-fg">
          {content}
          <span
            aria-hidden="true"
            className="ml-0.5 inline-block h-[1.05em] w-px bg-fg align-[-2px] motion-safe:animate-pulse"
          />
        </div>
      )}
    </div>
  );
}
