import type { ReactNode } from 'react';

interface TooltipProps {
  text: string;
  children: ReactNode;
  side?: 'top' | 'bottom';
}

/** A short label on hover or keyboard focus. */
export function Tooltip({ text, children, side = 'bottom' }: TooltipProps) {
  return (
    <span className="group/tip relative inline-flex">
      {children}
      <span
        role="tooltip"
        className={`pointer-events-none absolute left-1/2 z-50 -translate-x-1/2 whitespace-nowrap rounded-[5px] bg-fg px-2 py-[3px] text-xs font-medium text-canvas opacity-0 transition-opacity delay-300 group-hover/tip:opacity-100 group-focus-within/tip:opacity-100 ${
          side === 'top' ? 'bottom-full mb-1.5' : 'top-full mt-1.5'
        }`}
      >
        {text}
      </span>
    </span>
  );
}
