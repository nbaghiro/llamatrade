import { RISK_CHECKS } from '../../lib/sessionState';

/**
 * The seven pre-trade checks in order. Only a check named by the stopping reason is marked;
 * the others show as not recorded, because per-check results aren't stored yet.
 */
export function CheckLadder({ stopped }: { stopped: readonly number[] }) {
  return (
    <ol className="m-0 list-none p-0" aria-label="Risk checks">
      {RISK_CHECKS.map((name, i) => {
        const hit = stopped.includes(i);
        return (
          <li
            key={name}
            className={`grid h-10 grid-cols-[22px_minmax(0,1fr)_auto] items-center gap-2.5 border-b border-line px-3.5 text-[12.5px] last:border-b-0 ${
              hit ? 'bg-risk-soft shadow-[inset_2px_0_0_rgb(var(--risk))]' : ''
            }`}
          >
            <span className="num text-[11px] font-medium text-fg-3">{i + 1}</span>
            <span className="truncate">{name}</span>
            <span
              className={`text-right text-[11.5px] ${hit ? 'font-semibold text-risk' : 'text-fg-3'}`}
            >
              {hit ? 'Stopped' : 'Not recorded'}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
