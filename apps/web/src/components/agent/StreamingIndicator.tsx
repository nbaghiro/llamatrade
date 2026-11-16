interface StreamingIndicatorProps {
  content?: string;
}

/** Copilot's reply while it streams in, or three dots before the first words arrive. */
export function StreamingIndicator({ content }: StreamingIndicatorProps) {
  return (
    <div className="grid gap-1" aria-live="polite">
      <span className="font-mono text-[11px] font-medium text-fg-3">Copilot</span>
      {content ? (
        <div className="whitespace-pre-wrap text-[14px] leading-[1.55] text-fg">
          {content}
          <span
            aria-hidden="true"
            className="ml-0.5 inline-block h-[1.1em] w-0.5 bg-accent align-middle motion-safe:animate-pulse"
          />
        </div>
      ) : (
        <div className="flex items-center gap-1 py-1.5" aria-label="Copilot is replying">
          {[0, 150, 300].map((delay) => (
            <span
              key={delay}
              className="h-1.5 w-1.5 rounded-full bg-fg-3 motion-safe:animate-pulse"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
