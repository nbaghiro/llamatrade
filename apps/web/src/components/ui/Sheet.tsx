import { X } from 'lucide-react';
import { useId, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { useModal } from './useModal';

interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}

/** A full-height side sheet from the right; full width on phones. */
export function Sheet({ open, onClose, title, children, footer, width = 440 }: SheetProps) {
  const panel = useModal(open, onClose);
  const titleId = useId();
  if (!open) return null;
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex justify-end"
      style={{ background: 'var(--scrim)' }}
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="flex h-full w-full flex-col border-l border-line-strong bg-panel shadow-xl outline-none"
        style={{ maxWidth: width }}
      >
        <div className="flex items-center justify-between border-b border-line px-4 py-3.5">
          <b id={titleId} className="text-[15px] font-semibold">
            {title}
          </b>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="btn btn-ghost btn-sm px-1.5"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-line bg-sunk px-4 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
