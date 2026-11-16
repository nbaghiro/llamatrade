import { useFundingStore } from '@llamatrade/core/stores/funding';
import { useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { formatMoney } from '../../lib/format';
import {
  amountProblem,
  fundsPreview,
  parseAmount,
  QUICK_AMOUNTS,
  quickLabel,
  type AccountTotals,
} from '../../lib/portfolioView';
import { Dialog, Num } from '../ui';

interface AddFundsDialogProps {
  open: boolean;
  onClose: () => void;
  /** The account as it stands, for the before-and-after table. */
  totals: AccountTotals;
  onFunded: (amount: number) => void;
}

const DEFAULT_AMOUNT = QUICK_AMOUNTS[1];

function asInput(amount: number): string {
  return amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Adds paper money to unallocated cash through DepositFunds, showing where it lands first. */
export function AddFundsDialog({ open, onClose, totals, onFunded }: AddFundsDialogProps) {
  const { addFunds, submitting, error, clearError, resolveAccount, resolved, accountId } =
    useFundingStore();
  const [input, setInput] = useState(asInput(DEFAULT_AMOUNT));
  const [touched, setTouched] = useState(false);
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setInput(asInput(DEFAULT_AMOUNT));
    setTouched(false);
    clearError();
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [open, clearError]);

  useEffect(() => {
    if (open && !resolved) resolveAccount();
  }, [open, resolved, resolveAccount]);

  const amount = parseAmount(input);
  const problem = amountProblem(amount);
  const noAccount = resolved && !accountId;
  const preview = fundsPreview(totals, problem ? 0 : (amount ?? 0));

  const submit = async () => {
    setTouched(true);
    if (problem || amount === null || submitting) return;
    const result = await addFunds(amount);
    if (result !== null) {
      onFunded(amount);
      onClose();
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add paper funds"
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            form={`${inputId}-form`}
            className="btn btn-primary"
            disabled={submitting || noAccount || (touched && problem !== null)}
          >
            {submitting
              ? 'Adding…'
              : `Add ${amount !== null && !problem ? formatMoney(amount) : 'funds'}`}
          </button>
        </>
      }
    >
      <form
        id={`${inputId}-form`}
        className="grid min-w-0 gap-3.5"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label htmlFor={inputId} className="sr-only">
          Amount in dollars
        </label>
        <div
          className={`flex h-14 items-center gap-2 rounded-[8px] border bg-panel px-3 font-mono text-[26px] font-medium tracking-[-0.02em] focus-within:border-accent focus-within:shadow-[0_0_0_3px_var(--accent-soft)] ${
            touched && problem ? 'border-risk' : 'border-line-strong'
          }`}
        >
          <span className="text-fg-3">$</span>
          <input
            ref={inputRef}
            id={inputId}
            inputMode="decimal"
            autoComplete="off"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onBlur={() => setTouched(true)}
            aria-invalid={touched && problem !== null}
            aria-describedby={`${inputId}-note`}
            className="w-0 min-w-0 flex-1 bg-transparent outline-none"
          />
        </div>
        <div className="grid grid-cols-4 gap-1.5">
          {QUICK_AMOUNTS.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => {
                setInput(asInput(q));
                setTouched(false);
              }}
              aria-pressed={amount === q}
              className={`btn ${amount === q ? 'btn-primary' : 'btn-secondary'}`}
            >
              {quickLabel(q)}
            </button>
          ))}
        </div>
        {touched && problem && (
          <p role="alert" className="m-0 text-[12.5px] text-risk">
            {problem}
          </p>
        )}
      </form>

      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="font-mono text-[11px] text-fg-3">
            <th className="border-b border-line py-2 text-left font-medium" />
            <th className="border-b border-line py-2 text-right font-medium">Now</th>
            <th className="border-b border-line py-2 text-right font-medium">After</th>
          </tr>
        </thead>
        <tbody>
          {preview.map((row) => (
            <tr key={row.key} className={row.key === 'total' ? 'font-semibold' : ''}>
              <td className={`py-2 ${row.key === 'total' ? 'rule-total' : 'border-b border-line'}`}>
                {row.label}
              </td>
              <td
                className={`py-2 text-right ${row.key === 'total' ? 'rule-total' : 'border-b border-line'}`}
              >
                <Num value={row.now} />
              </td>
              <td
                className={`py-2 text-right ${row.key === 'total' ? 'rule-total' : 'border-b border-line'} ${
                  row.key === 'unallocated' && row.after !== row.now ? 'text-accent' : ''
                }`}
              >
                <Num value={row.after} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p id={`${inputId}-note`} className="m-0 text-[12.5px] text-fg-3">
        Paper money only. It lands in unallocated cash, and no sleeve changes until you deploy or
        top one up. There&apos;s no bank or card involved.
      </p>
      {noAccount && (
        <p role="alert" className="m-0 text-[12.5px] text-risk">
          No Alpaca paper account is connected yet.{' '}
          <Link to="/settings/broker" className="underline" onClick={onClose}>
            Connect one in Settings
          </Link>{' '}
          to add paper funds.
        </p>
      )}
      {error && !noAccount && (
        <p role="alert" className="m-0 text-[12.5px] text-risk">
          {error}
        </p>
      )}
    </Dialog>
  );
}
