import type { ReactNode } from 'react';

interface PillProps {
  children: ReactNode;
  /** Accent for selection, risk for attention; neutral otherwise. */
  tone?: 'neutral' | 'accent' | 'risk';
  dot?: boolean;
  className?: string;
  title?: string;
}

const TONE = {
  neutral: 'border-line-strong text-fg-2',
  accent: 'border-accent/50 bg-accent-soft text-accent',
  risk: 'border-risk-line bg-risk-soft text-risk',
} as const;

const DOT = { neutral: 'bg-fg-3', accent: 'bg-accent', risk: 'bg-risk' } as const;

export function Pill({
  children,
  tone = 'neutral',
  dot = false,
  className = '',
  title,
}: PillProps) {
  return (
    <span
      title={title}
      className={`inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full border px-[9px] font-mono text-[11.5px] font-medium ${TONE[tone]} ${className}`}
    >
      {dot && <i aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${DOT[tone]}`} />}
      {children}
    </span>
  );
}
