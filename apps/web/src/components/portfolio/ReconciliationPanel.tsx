import type { SleeveDetail } from '@llamatrade/core/stores/portfolio';

import { Num } from '../ui';

const STEP_BADGE =
  'grid h-6 w-6 flex-none place-items-center rounded-full border border-line-strong font-mono text-[11.5px] font-semibold text-fg-2';

/** What a frozen sleeve means and what can be done about it today, inside the sleeve's page. */
export function ReconciliationPanel({ sleeve }: { sleeve: SleeveDetail }) {
  const symbols = Object.keys(sleeve.ledgerQty).sort();

  return (
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
      <section className="panel">
        <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-line px-4 py-3">
          <b className="font-semibold">Ledger quantities</b>
          <span className="text-[12.5px] text-fg-3">Open lots in this sleeve</span>
        </div>
        <div className="grid gap-3 px-4 py-3.5">
          {symbols.length === 0 ? (
            <p className="m-0 text-[12.5px] text-fg-2">The ledger holds no open lots here.</p>
          ) : (
            symbols.map((sym) => (
              <div key={sym} className="flex items-center justify-between gap-3">
                <span className="font-mono text-[13px] font-semibold">{sym}</span>
                <span className="text-[12.5px] text-fg-2">
                  Ledger{' '}
                  <Num value={sleeve.ledgerQty[sym]} dp={sleeve.ledgerQty[sym] % 1 ? 4 : 0} />
                </span>
              </div>
            ))
          )}
          <p className="m-0 border-t border-line pt-3 text-[12.5px] text-fg-2">
            Reconciliation compares these counts with the positions Alpaca reports. Alpaca&apos;s
            counts and the symbol that disagreed aren&apos;t available on this page yet, so check
            them in your Alpaca paper dashboard. Sleeves that don&apos;t hold the symbol keep
            trading.
          </p>
        </div>
      </section>

      <div className="grid gap-4">
        <section className="panel">
          <div className="border-b border-line px-4 py-3">
            <b className="font-semibold">What you can do</b>
          </div>
          <ol className="m-0 grid list-none gap-3 p-4">
            <li className="flex items-start gap-3">
              <span className={STEP_BADGE}>1</span>
              <div>
                <b className="font-semibold">Check this sleeve&apos;s orders in Alpaca</b>
                <div className="text-[12.5px] text-fg-2">
                  A trade placed outside LlamaTrade, or a fill that hasn&apos;t reached the ledger
                  yet, would explain a different count.
                </div>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <span className={STEP_BADGE}>2</span>
              <div>
                <b className="font-semibold">Leave the holdings in place</b>
                <div className="text-[12.5px] text-fg-2">
                  Nothing is adjusted automatically. The positions stay as they are while the sleeve
                  is frozen.
                </div>
              </div>
            </li>
            <li className="flex items-start gap-3 opacity-55">
              <span className={STEP_BADGE}>3</span>
              <div>
                <b className="font-semibold">Adjust the ledger and resume</b>
                <div className="text-[12.5px] text-fg-2">Not available yet.</div>
              </div>
            </li>
          </ol>
        </section>
        <section className="panel">
          <div className="border-b border-line px-4 py-3">
            <b className="font-semibold">Held orders</b>
          </div>
          <p className="m-0 px-4 py-3.5 text-[12.5px] text-fg-2">
            New orders for this sleeve are rejected while it&apos;s frozen, including its next
            rebalance.
          </p>
        </section>
      </div>
    </div>
  );
}
