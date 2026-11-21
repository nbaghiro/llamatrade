import { useFundingStore } from '@llamatrade/core/stores/funding';
import type { SleeveSummary } from '@llamatrade/core/stores/portfolio';
import { Check } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { formatMoney } from '../../lib/format';
import {
  amountProblem,
  parseAmount,
  QUICK_AMOUNTS,
  quickLabel,
  type AccountTotals,
} from '../../lib/portfolioView';
import { nextRebalanceDate } from '../../lib/sessionState';
import { sleeveColor, sleeveRunState } from '../portfolio/sleeveView';
import { dayLabel, etToday } from '../sessions/sessionRows';
import { Dialog, ModeBadge, Money } from '../ui';

import { PaperBar } from './PaperBar';
import {
  allocateToSleeve,
  beforeAfter,
  placed,
  placementProblem,
  type Placement,
} from './placement';

interface AddFundsDialogProps {
  open: boolean;
  onClose: () => void;
  /** The paper account as it stands. */
  totals: AccountTotals;
  /** Paper sleeves, offered as places for the new money. */
  sleeves?: readonly SleeveSummary[];
  onFunded: (amount: number) => void;
}

type Step = 'amount' | 'where' | 'confirm';
const STEPS: readonly { key: Step; label: string }[] = [
  { key: 'amount', label: 'Amount' },
  { key: 'where', label: 'Where it goes' },
  { key: 'confirm', label: 'Confirm' },
];

const DEFAULT_AMOUNT = QUICK_AMOUNTS[0];
const UNALLOCATED_COLOR = 'rgb(var(--fg-3) / 0.35)';

function asInput(amount: number): string {
  return amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Why a sleeve can't take money right now, or null when it can. */
function closedReason(s: SleeveSummary): string | null {
  const state = sleeveRunState(s);
  if (!s.sleeveId) return "the ledger can't see it";
  if (state === 'stopped') return "stopped, can't take money";
  if (state === 'frozen') return "frozen, can't take money";
  return null;
}

function rebalanceNote(s: SleeveSummary, today: Date): string {
  const at = nextRebalanceDate(s.rebalance, today);
  return at ? `next ${dayLabel(at)}` : s.rebalance ? `rebalances ${s.rebalance.toLowerCase()}` : '';
}

function Steps({ step }: { step: Step }) {
  const at = STEPS.findIndex((s) => s.key === step);
  return (
    <ol className="m-0 flex list-none items-center gap-2 p-0 text-[12.5px]">
      {STEPS.map((s, i) => (
        <li key={s.key} className="flex items-center gap-2">
          {i > 0 && <span aria-hidden="true" className="h-px w-6 bg-line-strong" />}
          <span
            className={`grid h-[18px] w-[18px] place-items-center rounded-full font-mono text-[10.5px] ${
              i < at
                ? 'bg-fg-3 text-canvas'
                : i === at
                  ? 'bg-fg text-canvas'
                  : 'border border-line-strong text-fg-3'
            }`}
          >
            {i < at ? <Check aria-hidden="true" className="h-3 w-3" /> : i + 1}
          </span>
          <span
            className={i === at ? 'text-fg' : 'text-fg-3'}
            aria-current={i === at ? 'step' : undefined}
          >
            {s.label}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Add paper money, then place it: unallocated by default, or a top-up to sleeves (add-funds2 A). */
export function AddFundsDialog({
  open,
  onClose,
  totals,
  sleeves = [],
  onFunded,
}: AddFundsDialogProps) {
  const { addFunds, submitting, error, clearError, resolveAccount, resolved, accountId } =
    useFundingStore();
  const [step, setStep] = useState<Step>('amount');
  const [input, setInput] = useState(asInput(DEFAULT_AMOUNT));
  const [touched, setTouched] = useState(false);
  const [topUp, setTopUp] = useState(false);
  const [placement, setPlacement] = useState<Placement>({});
  const [placing, setPlacing] = useState(false);
  const [placeError, setPlaceError] = useState<string | null>(null);
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const today = etToday();

  useEffect(() => {
    if (!open) return;
    setStep('amount');
    setInput(asInput(DEFAULT_AMOUNT));
    setTouched(false);
    setTopUp(false);
    setPlacement({});
    setPlaceError(null);
    clearError();
  }, [open, clearError]);

  useEffect(() => {
    if (open && step === 'amount') {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [open, step]);

  useEffect(() => {
    if (open && !resolved) resolveAccount();
  }, [open, resolved, resolveAccount]);

  const amount = parseAmount(input);
  const problem = amountProblem(amount);
  const deposit = problem ? 0 : (amount ?? 0);
  const noAccount = resolved && !accountId;
  const openSleeves = sleeves.filter((s) => closedReason(s) === null);
  const effective: Placement = topUp ? placement : {};
  const placeProblem = topUp ? placementProblem(deposit, placement) : null;

  const indexOf = useMemo(
    () => new Map(sleeves.map((s, i) => [s.sleeveId ?? s.executionId, i])),
    [sleeves]
  );
  const colorOf = (id: string) =>
    id === 'unallocated' ? UNALLOCATED_COLOR : sleeveColor(indexOf.get(id) ?? 0);
  const bars = beforeAfter(
    sleeves.map((s) => ({ id: s.sleeveId ?? s.executionId, value: s.value })),
    totals.unallocated,
    deposit,
    effective
  );
  const moved = placed(effective);
  const firstTopped = sleeves.find((s) => s.sleeveId && (effective[s.sleeveId] ?? 0) > 0);

  const chooseTopUp = () => {
    setTopUp(true);
    if (placed(placement) === 0 && openSleeves[0]?.sleeveId) {
      setPlacement({ [openSleeves[0].sleeveId]: deposit });
    }
  };

  const submit = async () => {
    if (amount === null || problem || submitting || placing) return;
    setPlaceError(null);
    const result = await addFunds(amount);
    if (result === null) return;
    const accountNow = useFundingStore.getState().accountId;
    const failed: string[] = [];
    if (accountNow && moved > 0) {
      setPlacing(true);
      for (const s of sleeves) {
        const add = s.sleeveId ? (effective[s.sleeveId] ?? 0) : 0;
        if (!s.sleeveId || add <= 0) continue;
        const err = await allocateToSleeve(accountNow, s.sleeveId, add);
        if (err) failed.push(s.name);
      }
      setPlacing(false);
    }
    onFunded(amount);
    if (failed.length) {
      setPlaceError(
        `${formatMoney(amount)} was added, but the top-up to ${failed.join(' and ')} didn't go through. That money is in unallocated cash.`
      );
      return;
    }
    onClose();
  };

  const next = () => {
    setTouched(true);
    if (step === 'amount' && !problem && !noAccount) setStep('where');
    else if (step === 'where' && !placeProblem) setStep('confirm');
  };

  const footer = (
    <div className="flex w-full flex-wrap items-center justify-between gap-3">
      <span className="text-[12.5px] text-fg-3">
        Paper money only. Live deposits happen in Alpaca.
      </span>
      <div className="flex gap-2">
        {step === 'amount' ? (
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setStep(step === 'confirm' ? 'where' : 'amount')}
            disabled={submitting || placing}
          >
            Back
          </button>
        )}
        {step === 'confirm' ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={submit}
            disabled={submitting || placing || noAccount}
          >
            {submitting ? 'Adding…' : placing ? 'Topping up…' : `Add ${formatMoney(deposit)}`}
          </button>
        ) : (
          <button
            type="submit"
            form={`${inputId}-form`}
            className="btn btn-primary"
            disabled={
              noAccount ||
              (touched && (step === 'amount' ? problem !== null : placeProblem !== null))
            }
          >
            Continue
          </button>
        )}
      </div>
    </div>
  );

  return (
    <Dialog open={open} onClose={onClose} title="Add paper funds" width={580} footer={footer}>
      <Steps step={step} />
      <form
        id={`${inputId}-form`}
        className="grid min-w-0 gap-3.5"
        onSubmit={(e) => {
          e.preventDefault();
          next();
        }}
      >
        {step === 'amount' ? (
          <>
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
            <p className="m-0 text-[12.5px] text-fg-3">
              There&apos;s no bank or card involved. Next you choose whether it waits in unallocated
              cash or tops up a sleeve.
            </p>
          </>
        ) : (
          <div className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2.5">
              <span className="num text-[22px] font-medium">{formatMoney(deposit)}</span>
              <ModeBadge mode="paper" size="sm" />
            </span>
            <button
              type="button"
              className="text-[12.5px] text-accent hover:underline"
              onClick={() => setStep('amount')}
            >
              Change amount
            </button>
          </div>
        )}

        {step === 'where' && (
          <div role="radiogroup" aria-label="Where it goes" className="grid gap-2">
            <label
              className={`flex cursor-pointer gap-3 rounded-[8px] border px-3.5 py-3 ${
                !topUp ? 'border-accent shadow-[0_0_0_1px_rgb(var(--accent)/0.4)]' : 'border-line'
              }`}
            >
              <input
                type="radio"
                name={`${inputId}-where`}
                checked={!topUp}
                onChange={() => setTopUp(false)}
                className="mt-1 accent-[rgb(var(--accent))]"
              />
              <span>
                <b className="font-semibold">Keep it unallocated</b>
                <span className="block text-[12.5px] text-fg-2">
                  It waits in paper cash until you start a strategy or top up a sleeve.
                </span>
              </span>
            </label>
            <div
              className={`rounded-[8px] border px-3.5 py-3 ${
                topUp ? 'border-accent shadow-[0_0_0_1px_rgb(var(--accent)/0.4)]' : 'border-line'
              } ${openSleeves.length === 0 ? 'opacity-55' : ''}`}
            >
              <label className="flex cursor-pointer gap-3">
                <input
                  type="radio"
                  name={`${inputId}-where`}
                  checked={topUp}
                  disabled={openSleeves.length === 0}
                  onChange={chooseTopUp}
                  className="mt-1 accent-[rgb(var(--accent))]"
                />
                <span>
                  <b className="font-semibold">Top up a sleeve now</b>
                  <span className="block text-[12.5px] text-fg-2">
                    {openSleeves.length === 0
                      ? 'No paper sleeve can take money right now.'
                      : 'The sleeve holds it as cash and invests it at its next rebalance.'}
                  </span>
                </span>
              </label>
              {topUp && (
                <div className="mt-2.5 grid gap-1.5 pl-7">
                  {sleeves.map((s, i) => {
                    const reason = closedReason(s);
                    const id = s.sleeveId ?? s.executionId;
                    const value = placement[id] ?? 0;
                    const on = value > 0;
                    return (
                      <div
                        key={id}
                        className={`flex items-center gap-2.5 text-[13px] ${reason ? 'text-fg-3' : ''}`}
                      >
                        <input
                          type="checkbox"
                          aria-label={`Top up ${s.name}`}
                          checked={on}
                          disabled={reason !== null}
                          onChange={(e) =>
                            setPlacement((p) => ({
                              ...p,
                              [id]: e.target.checked ? Math.max(0, deposit - placed(p)) : 0,
                            }))
                          }
                          className="accent-[rgb(var(--accent))]"
                        />
                        <i
                          aria-hidden="true"
                          className="h-2 w-2 flex-none rounded-[2px]"
                          style={{ background: sleeveColor(i), opacity: reason ? 0.4 : 1 }}
                        />
                        <span className="min-w-0 flex-1 truncate">{s.name}</span>
                        <span className="hidden text-[11.5px] text-fg-3 sm:inline">
                          {reason ?? rebalanceNote(s, today)}
                        </span>
                        {!reason && (
                          <input
                            inputMode="decimal"
                            aria-label={`Amount for ${s.name}`}
                            value={on ? asInput(value) : ''}
                            placeholder="$0"
                            onChange={(e) => {
                              const v = parseAmount(e.target.value) ?? 0;
                              setPlacement((p) => ({ ...p, [id]: v }));
                            }}
                            className="h-8 w-[110px] rounded-[6px] border border-line-strong bg-panel px-2 text-right font-mono text-[13px] outline-none focus:border-accent"
                          />
                        )}
                      </div>
                    );
                  })}
                  {touched && placeProblem && (
                    <p role="alert" className="m-0 text-[12.5px] text-risk">
                      {placeProblem}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {step === 'confirm' && (
          <ul className="m-0 grid list-none gap-1.5 p-0 text-[13px]">
            <li>
              Add <Money value={deposit} /> of paper money to the Alpaca paper account.
            </li>
            {moved < deposit && (
              <li>
                <Money value={deposit - moved} /> stays in unallocated cash.
              </li>
            )}
            {sleeves
              .filter((s) => s.sleeveId && (effective[s.sleeveId] ?? 0) > 0)
              .map((s) => {
                const at = nextRebalanceDate(s.rebalance, today);
                return (
                  <li key={s.executionId}>
                    <Money value={effective[s.sleeveId ?? ''] ?? 0} /> tops up {s.name}. It&apos;s
                    held as cash and invested at the next rebalance
                    {at ? `, ${dayLabel(at)}` : ''}.
                  </li>
                );
              })}
          </ul>
        )}
      </form>

      {step !== 'amount' && (
        <div className="grid grid-cols-[64px_minmax(0,1fr)] items-center gap-x-3 gap-y-2 text-[12.5px] text-fg-2">
          <span>Paper now</span>
          <PaperBar parts={bars.now} colorOf={colorOf} label="The paper account now" />
          <span>After</span>
          <PaperBar parts={bars.after} colorOf={colorOf} label="The paper account after" />
          <span />
          <div className="flex flex-wrap justify-between gap-x-3 text-[11.5px] text-fg-3">
            <span className="num">
              {formatMoney(totals.total)} →{' '}
              <b className="text-fg">{formatMoney(totals.total + deposit)}</b>
            </span>
            {firstTopped && (
              <span className="num">
                {firstTopped.name} {formatMoney(firstTopped.value)} →{' '}
                <b className="text-fg">
                  {formatMoney(firstTopped.value + (effective[firstTopped.sleeveId ?? ''] ?? 0))}
                </b>
              </span>
            )}
          </div>
        </div>
      )}

      {noAccount && (
        <p role="alert" className="m-0 text-[12.5px] text-risk">
          No Alpaca paper account is connected yet.{' '}
          <Link to="/settings/broker" className="underline" onClick={onClose}>
            Connect one in Settings
          </Link>{' '}
          to add paper funds.
        </p>
      )}
      {(error || placeError) && !noAccount && (
        <p role="alert" className="m-0 text-[12.5px] text-risk">
          {placeError ?? error}
        </p>
      )}
    </Dialog>
  );
}
