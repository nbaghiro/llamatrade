import type { ReactNode } from 'react';

export function Kbd({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={`rounded-[4px] border border-line-strong px-[5px] py-px font-mono text-[10.5px] font-medium text-fg-3 ${className}`}
    >
      {children}
    </kbd>
  );
}
