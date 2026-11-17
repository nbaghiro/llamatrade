import { formatNumber } from '../../lib/format';

import { dayLabel } from './sessionRows';
import type { StopHolding } from './StopDialog';

const qty = (v: number) => formatNumber(v, { dp: Number.isInteger(v) ? 0 : 2 });

/**
 * Beside a frozen sleeve: what the ledger records and what can be done here (frozen2 A). Recording
 * which count is right and resuming the sleeve have no endpoint yet, so those steps are described,
 * not offered.
 */
export function FrozenPanel({
  name,
  holdings,
  next,
  onStop,
}: {
  name: string;
  holdings: readonly StopHolding[];
  next: Date | null;
  onStop: () => void;
}) {
  return (
    <section
      aria-label="Resolve the freeze"
      className="overflow-hidden rounded-panel border border-risk-line bg-panel"
    >
      <header className="border-b border-line px-4 py-3">
        <h2 className="m-0 font-sans text-[13.5px] font-semibold">Resolving the freeze</h2>
        <p className="m-0 mt-0.5 text-[12px] text-fg-3">Nothing changes until you act.</p>
      </header>
      <ol className="m-0 grid list-none gap-4 p-4">
        <Step n={1} title="Compare the counts">
          The ledger and Alpaca disagree about what this sleeve holds. The ledger records the
          quantities below; check them against the positions in your Alpaca dashboard.
          {holdings.length > 0 && (
            <dl className="m-0 mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-[8px] border border-line px-3 py-2 font-mono text-[12px]">
              {holdings.map((h) => (
                <div key={h.symbol} className="contents">
                  <dt className="font-semibold">{h.symbol}</dt>
                  <dd className="m-0 text-right">{qty(h.quantity)} in the ledger</dd>
                </div>
              ))}
            </dl>
          )}
        </Step>
        <Step n={2} title="Choose which count is right">
          Recording a resolution can&apos;t be done in the app yet. An order placed directly in the
          Alpaca dashboard is the usual cause of a difference.
        </Step>
        <Step n={3} title="Resume the sleeve">
          The sleeve resumes once the two agree.
          {next ? ` Orders start again from the ${dayLabel(next)} rebalance.` : ''}
        </Step>
      </ol>
      <footer className="grid gap-2 border-t border-line px-4 py-3">
        <p className="m-0 text-[12px] text-fg-2">
          If you&apos;d rather not wait, stopping {name} moves its holdings to Unmanaged in your
          Alpaca account, where nothing trades them.
        </p>
        <button type="button" className="btn btn-secondary" onClick={onStop}>
          Stop the session
        </button>
        <p className="m-0 text-center text-[11.5px] text-fg-3">
          Your other sessions keep running as usual.
        </p>
      </footer>
    </section>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <li className="grid grid-cols-[24px_minmax(0,1fr)] gap-3">
      <span className="grid h-6 w-6 place-items-center rounded-full border border-line-strong font-mono text-[11px] text-fg-2">
        {n}
      </span>
      <div className="text-[12.5px] text-fg-2">
        <b className="mb-0.5 block text-[13px] font-semibold text-fg">{title}</b>
        {children}
      </div>
    </li>
  );
}
