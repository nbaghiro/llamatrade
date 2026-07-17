/**
 * Add-funds form — credits paper capital into the account's Unallocated sleeve,
 * the pool every strategy allocates from. Shared by the modal and the Wallet page.
 */

import { useFundingStore } from '@llamatrade/core/stores/funding';
import { useEffect, useState } from 'react';


const PRESETS = [10_000, 25_000, 50_000, 100_000];
/** Guards against a fat-fingered extra zero; deposits are whole dollars. */
const MAX_DEPOSIT = 1_000_000;

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

interface AddFundsFormProps {
  /** Called with the new allocatable balance once the deposit lands. */
  onFunded: (newFreeCash: number) => void;
  autoFocus?: boolean;
}

export function AddFundsForm({ onFunded, autoFocus = false }: AddFundsFormProps) {
  const {
    addFunds,
    submitting,
    error,
    clearError,
    resolved,
    resolving,
    accountId,
    resolveAccount,
    unallocatedCash: freeCash,
  } = useFundingStore();
  const [raw, setRaw] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (!resolved && !resolving) void resolveAccount();
  }, [resolved, resolving, resolveAccount]);

  const digits = raw.replace(/\D/g, '');
  const amount = digits ? parseInt(digits, 10) : 0;
  const display = digits ? amount.toLocaleString('en-US') : '';
  const tooLarge = amount > MAX_DEPOSIT;
  const canSubmit = amount > 0 && !tooLarge && !submitting && accountId !== null;

  const setAmount = (next: number) => {
    setRaw(String(next));
    setLocalError(null);
    clearError();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (amount <= 0) {
      setLocalError('Enter an amount greater than $0.');
      return;
    }
    if (tooLarge) {
      setLocalError(`Enter an amount up to ${formatCurrency(MAX_DEPOSIT)}.`);
      return;
    }
    const newFree = await addFunds(amount);
    if (newFree !== null) {
      setRaw('');
      setLocalError(null);
      onFunded(newFree);
    }
  };

  // No broker credential yet → nothing to anchor an account to.
  if (resolved && !accountId) {
    return (
      <div className="border-2 border-ink bg-bone p-4">
        <div className="font-mono text-[9.5px] font-bold uppercase tracking-[0.13em] text-ink/50">
          No paper account
        </div>
        <p className="mt-2 text-[13px] leading-relaxed text-ink/70">
          Connect Alpaca paper keys to open an account before adding funds.
        </p>
      </div>
    );
  }

  const shown = localError ?? error;

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3.5">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[9.5px] font-bold uppercase tracking-[0.13em] text-ink/50">
          Free to allocate
        </span>
        <span className="font-mono text-xs font-bold tabular-nums text-ink">
          {formatCurrency(freeCash)}
        </span>
      </div>

      <div
        className={`flex items-center border-2 bg-bone transition-colors ${
          shown ? 'border-red-600' : 'border-ink focus-within:border-orange-500'
        }`}
      >
        <span className="pl-4 pr-1.5 font-mono text-[28px] font-bold leading-none text-ink/35">$</span>
        <input
          value={display}
          onChange={(e) => {
            setRaw(e.target.value);
            setLocalError(null);
            clearError();
          }}
          inputMode="numeric"
          autoFocus={autoFocus}
          placeholder="0"
          aria-label="Amount to add"
          aria-invalid={shown ? true : undefined}
          className="w-full bg-transparent py-3.5 pr-4 font-mono text-[28px] font-bold leading-none tabular-nums tracking-tight text-ink placeholder-ink/25 focus:outline-none"
        />
      </div>

      <div className="grid grid-cols-4 gap-2">
        {PRESETS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setAmount(p)}
            className={`border-2 border-ink py-2 font-mono text-[11px] font-bold tabular-nums shadow-[2px_2px_0_rgb(var(--lt-ink))] transition-transform hover:-translate-y-0.5 ${
              amount === p ? 'bg-ink text-bone' : 'bg-paper text-ink'
            }`}
          >
            +{p / 1000}K
          </button>
        ))}
      </div>

      {shown && (
        <p role="alert" className="font-mono text-[11px] font-bold text-red-600">
          {shown}
        </p>
      )}

      <p className="text-[11.5px] leading-relaxed text-ink/55">
        <b className="text-ink">Paper funds are simulated</b> — no real money moves.
        {amount > 0 && !tooLarge && (
          <>
            {' '}
            New balance{' '}
            <b className="font-mono tabular-nums text-ink">{formatCurrency(freeCash + amount)}</b>.
          </>
        )}
      </p>

      <button
        type="submit"
        disabled={!canSubmit}
        className="flex w-full items-center justify-center gap-2 border-2 border-ink bg-orange-500 py-3 font-mono text-[11px] font-bold uppercase tracking-[0.05em] text-ink shadow-[3px_3px_0_rgb(var(--lt-ink))] transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none disabled:hover:translate-y-0"
      >
        {submitting ? 'Adding…' : amount > 0 ? `Add ${formatCurrency(amount)} →` : 'Add funds →'}
      </button>
    </form>
  );
}
