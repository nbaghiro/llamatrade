import type { ReactNode } from 'react';

import { MARKETING_URL } from '../../config/marketing';
import { Logo } from '../common/Logo';

import { AuthShowcase } from './AuthShowcase';

interface AuthSplitLayoutProps {
  /** Anton display heading, e.g. "Sign In" (rendered uppercase). */
  title: string;
  /** Space-Mono caption beneath the heading. */
  subtitle: string;
  /** Form + cross-link content for the right panel. */
  children: ReactNode;
}

/**
 * AuthSplitLayout — shared half-split shell for the auth pages.
 *
 * On `lg+` the animated Monolith showcase fills ~56% on the left and the form
 * panel ~44% on the right. On small screens the showcase is replaced by a compact
 * branded ink header and the form takes the full width, so it is always usable.
 */
export function AuthSplitLayout({ title, subtitle, children }: AuthSplitLayoutProps) {
  return (
    <div className="flex min-h-screen w-full flex-col bg-bone lg:flex-row">
      {/* Left showcase — lg+ only (self-hides below lg). */}
      <AuthShowcase />

      <main className="flex flex-1 flex-col lg:min-h-screen lg:w-[44%]">
        <div className="flex items-center border-b-2 border-ink bg-ink px-5 py-4 lg:hidden">
          <a
            href={MARKETING_URL}
            aria-label="LlamaTrade — back to home"
            className="flex items-center gap-3 transition-opacity hover:opacity-80"
          >
            <Logo size={34} />
            <div className="leading-none">
              <div className="font-display text-lg uppercase tracking-tight text-bone">LlamaTrade</div>
              <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-bone/55">
                Algorithmic Trading
              </div>
            </div>
          </a>
        </div>

        <div className="flex flex-1 items-center justify-center px-5 py-10 sm:px-8">
          <div className="w-full max-w-sm">
            <header className="mb-7">
              <h1 className="font-display text-4xl uppercase tracking-tight text-ink sm:text-5xl">
                {title}
              </h1>
              <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.14em] text-ink/55">
                {subtitle}
              </p>
              <div className="mt-4 h-1 w-16 bg-orange-500" aria-hidden="true" />
            </header>

            {children}
          </div>
        </div>
      </main>
    </div>
  );
}
