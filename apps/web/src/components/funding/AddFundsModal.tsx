/**
 * Quick-add funds overlay — the fast path to credit paper capital from anywhere
 * the free-cash balance is shown. Wraps the shared <AddFundsForm>.
 */

import { X } from 'lucide-react';
import { useEffect } from 'react';

import { AddFundsForm } from './AddFundsForm';

interface AddFundsModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Fired after a successful deposit so the caller can refresh balances. */
  onFunded: (newFreeCash: number) => void;
}

export function AddFundsModal({ isOpen, onClose, onFunded }: AddFundsModalProps) {
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleFunded = (newFreeCash: number) => {
    onFunded(newFreeCash);
    onClose();
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Add funds"
          className="w-full max-w-[440px] border-2 border-ink bg-paper shadow-[5px_5px_0_#ff4d1c]"
        >
          <div className="flex items-center justify-between border-b-2 border-ink bg-ink px-4 py-3 text-bone">
            <span className="font-display text-base uppercase tracking-tight">Add funds</span>
            <button
              onClick={onClose}
              aria-label="Close"
              className="grid h-6 w-6 place-items-center border-2 border-bone/30 text-bone transition-colors hover:border-bone"
            >
              <X className="h-3.5 w-3.5" strokeWidth={2.6} />
            </button>
          </div>
          <div className="p-5">
            <AddFundsForm onFunded={handleFunded} autoFocus />
          </div>
        </div>
      </div>
    </>
  );
}
