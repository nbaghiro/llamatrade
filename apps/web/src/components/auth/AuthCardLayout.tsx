import type { ReactNode } from 'react';

import { AuthBrand } from './AuthSplitLayout';

interface AuthCardLayoutProps {
  children: ReactNode;
  /** One quiet line under the card. */
  footnote?: string;
}

/** One small centred card on a dotted ground for short tasks; on phones the card's frame drops away. */
export function AuthCardLayout({ children, footnote }: AuthCardLayoutProps) {
  return (
    <div className="auth-shell grid min-h-screen bg-canvas px-4 py-5 sm:bg-dots sm:place-items-center sm:py-10">
      <div className="grid w-full max-w-[420px] content-start gap-6 sm:gap-4">
        <AuthBrand className="sm:justify-self-center" />
        <main className="grid gap-3.5 sm:rounded-[12px] sm:border sm:border-line sm:bg-panel sm:p-[26px] sm:shadow-lg">
          {children}
        </main>
        {footnote && <p className="m-0 text-[12.5px] text-fg-3 sm:text-center">{footnote}</p>}
      </div>
    </div>
  );
}

const BIG_TONE = {
  neutral: 'bg-sunk text-fg-2',
  ok: 'bg-accent-soft text-accent',
  warn: 'bg-risk-soft text-risk',
} as const;

/** The large icon at the top of a result card: verified, saved or expired. */
export function CardIcon({ tone, children }: { tone: keyof typeof BIG_TONE; children: ReactNode }) {
  return (
    <div
      aria-hidden="true"
      className={`grid h-12 w-12 place-items-center rounded-[12px] [&_svg]:h-[22px] [&_svg]:w-[22px] ${BIG_TONE[tone]}`}
    >
      {children}
    </div>
  );
}
