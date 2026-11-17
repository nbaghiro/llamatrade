import type { PathStep } from './accountPaths';

function StepNumber({ n, on }: { n: number; on: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`num grid h-[22px] w-[22px] flex-none place-items-center rounded-full text-[11.5px] font-semibold ${
        on ? 'bg-fg text-canvas' : 'border border-line-strong text-fg-3'
      }`}
    >
      {n}
    </span>
  );
}

/** Backtest, paper, live as three numbered columns in one panel; the first step is current. */
export function AccountPath({
  steps,
  label = 'Where your account starts',
  className = '',
}: {
  steps: readonly PathStep[];
  label?: string;
  className?: string;
}) {
  return (
    <ol
      aria-label={label}
      className={`m-0 grid list-none gap-3 rounded-panel border border-line bg-panel px-4 py-3.5 sm:grid-cols-3 sm:gap-5 ${className}`}
    >
      {steps.map((s, i) => (
        <li
          key={s.title}
          className="flex items-start gap-2.5"
          aria-current={i === 0 ? 'step' : undefined}
        >
          <StepNumber n={i + 1} on={i === 0} />
          <div className="min-w-0">
            <b className="block text-[13px] font-semibold text-fg">{s.title}</b>
            <span className="block text-[11.5px] text-fg-3">{s.sub}</span>
          </div>
        </li>
      ))}
    </ol>
  );
}

/** The same path as one compact line for phones: Backtest, Paper, Live joined by rules. */
export function AccountPathLine({
  steps = ['Backtest', 'Paper', 'Live'],
  className = '',
}: {
  steps?: readonly string[];
  className?: string;
}) {
  return (
    <ol
      aria-label="Backtest now, paper and live later"
      className={`m-0 flex list-none items-center gap-2 p-0 text-[12px] ${className}`}
    >
      {steps.map((s, i) => (
        <li key={s} className="contents">
          {i > 0 && <i aria-hidden="true" className="h-px flex-1 bg-line-strong" />}
          <span
            aria-current={i === 0 ? 'step' : undefined}
            className={`rounded-full px-2.5 py-[3px] ${
              i === 0 ? 'bg-fg font-semibold text-canvas' : 'border border-line-strong text-fg-3'
            }`}
          >
            {s}
          </span>
        </li>
      ))}
    </ol>
  );
}
