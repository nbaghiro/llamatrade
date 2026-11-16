import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react';

import { useDismiss } from './useDismiss';

interface PopoverProps {
  /** Renders the trigger; spread `props` onto the button. */
  trigger: (props: {
    onClick: () => void;
    'aria-expanded': boolean;
    'aria-haspopup': 'dialog' | 'menu';
  }) => ReactNode;
  children: (close: () => void) => ReactNode;
  width?: number;
  align?: 'left' | 'right';
  role?: 'dialog' | 'menu';
  label?: string;
  className?: string;
}

/** A panel anchored under its trigger that closes on Escape or an outside press. */
export function Popover({
  trigger,
  children,
  width = 320,
  align = 'right',
  role = 'dialog',
  label,
  className = '',
}: PopoverProps) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  const refs = useMemo(() => [root], []);
  useDismiss(open, close, refs);
  return (
    <div ref={root} className="relative">
      {trigger({ onClick: () => setOpen((o) => !o), 'aria-expanded': open, 'aria-haspopup': role })}
      {open && (
        <div
          role={role}
          aria-label={label}
          className={`absolute top-full z-50 mt-2 overflow-hidden rounded-[12px] border border-line-strong bg-panel shadow-lg ${
            align === 'right' ? 'right-0' : 'left-0'
          } ${className}`}
          style={{ width, maxWidth: 'calc(100vw - 24px)' }}
        >
          {children(close)}
        </div>
      )}
    </div>
  );
}
