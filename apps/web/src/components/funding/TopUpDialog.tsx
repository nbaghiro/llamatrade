import { useFundingStore } from '@llamatrade/core/stores/funding';
import { useEffect, useId, useState } from 'react';

import { formatMoney } from '../../lib/format';
import { parseAmount } from '../../lib/portfolioView';
import { nextRebalanceDate } from '../../lib/sessionState';
import { dayLabel, etToday } from '../sessions/sessionRows';
import { Dialog } from '../ui';

import { allocateToSleeve, placementProblem } from './placement';

interface TopUpDialogProps {
  open: boolean;
  onClose: () => void;
  sleeve: { sleeveId: string; name: string; value: number; rebalance: string };
  onDone: () => void;
}

/** Moves unallocated paper cash into one sleeve (allocate A). */
export function TopUpDialog({ open, onClose, sleeve, onDone }: TopUpDialogProps) {
  const { unallocatedCash, accountId, resolved, resolveAccount } = useFundingStore();
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    setInput('');
    setError(null);
    resolveAccount();
  }, [open, resolveAccount]);

  const available = Math.max(0, unallocatedCash);
  const amount = parseAmount(input) ?? 0;
  const problem = placementProblem(available, { [sleeve.sleeveId]: amount });
  const at = nextRebalanceDate(sleeve.rebalance, etToday());

  const submit = async () => {
    if (problem || !accountId || busy) return;
    setBusy(true);
    const err = await allocateToSleeve(accountId, sleeve.sleeveId, amount);
    setBusy(false);
    if (err) {
      setError(err);
      return;
    }
    await useFundingStore.getState().resolveAccount();
    onDone();
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={`Top up ${sleeve.name}`}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={submit}
            disabled={busy || amount <= 0 || problem !== null || !accountId}
          >
            {busy ? 'Moving…' : `Move ${formatMoney(amount)}`}
          </button>
        </>
      }
    >
      {resolved && available <= 0 ? (
        <p className="m-0 text-[13px] text-fg-2">
          There&apos;s no unallocated paper cash to move. Add paper funds from Portfolio first.
        </p>
      ) : (
        <>
          <label htmlFor={id} className="text-[12.5px] text-fg-2">
            Amount, up to {formatMoney(available)} unallocated
          </label>
          <input
            id={id}
            inputMode="decimal"
            autoComplete="off"
            value={input}
            placeholder="0.00"
            onChange={(e) => setInput(e.target.value)}
            className="h-12 rounded-[8px] border border-line-strong bg-panel px-3 font-mono text-[22px] outline-none focus:border-accent"
          />
          <input
            type="range"
            aria-label="Amount"
            min={0}
            max={Math.floor(available)}
            step={100}
            value={Math.min(amount, available)}
            onChange={(e) => setInput(Number(e.target.value).toFixed(2))}
            className="accent-[rgb(var(--accent))]"
          />
          <div className="grid gap-1 text-[13px]">
            <div className="flex justify-between gap-3">
              <span className="text-fg-2">Unallocated</span>
              <span className="num">
                {formatMoney(available)} → {formatMoney(Math.max(0, available - amount))}
              </span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-fg-2">{sleeve.name}</span>
              <span className="num">
                {formatMoney(sleeve.value)} → {formatMoney(sleeve.value + amount)}
              </span>
            </div>
          </div>
          <p className="m-0 text-[12.5px] text-fg-3">
            The sleeve holds it as cash and invests it at its next rebalance
            {at ? `, ${dayLabel(at)}` : ''}. No orders are placed now.
          </p>
          {input && problem && amount > 0 && (
            <p role="alert" className="m-0 text-[12.5px] text-risk">
              {problem}
            </p>
          )}
        </>
      )}
      {error && (
        <p role="alert" className="m-0 text-[12.5px] text-risk">
          {error}
        </p>
      )}
    </Dialog>
  );
}
