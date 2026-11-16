import type { ReactNode } from 'react';

import { MARKETING_URL } from '../../config/marketing';
import { LogoMark } from '../common/Logo';

import { AuthArt } from './AuthArt';
import { ExampleBacktestPanel, ExampleBacktestStrip } from './ExampleBacktestPanel';

interface AuthSplitLayoutProps {
  title: string;
  subtitle: string;
  children: ReactNode;
}

export function AuthBrand({ className = '' }: { className?: string }) {
  return (
    <a
      href={MARKETING_URL}
      aria-label="LlamaTrade home"
      className={`inline-flex items-center gap-3.5 text-fg ${className}`}
    >
      <LogoMark size={44} bold className="-my-2" />
      <span className="text-[12.5px] font-semibold uppercase leading-none tracking-[0.16em]">
        LlamaTrade
      </span>
    </a>
  );
}

export function FormHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header>
      <h1 className="m-0 text-[22px] font-semibold leading-tight tracking-[-0.02em]">{title}</h1>
      <p className="mb-0 mt-[5px] text-[13px] text-fg-2">{subtitle}</p>
    </header>
  );
}

/**
 * The sign-in shell: the form on the left and the example backtest on the right. Below 768px the
 * example becomes a strip above the form.
 */
export function AuthSplitLayout({ title, subtitle, children }: AuthSplitLayoutProps) {
  return (
    <div className="auth-shell min-h-screen bg-canvas md:grid md:grid-cols-2 lg:grid-cols-[500px_minmax(0,1fr)]">
      <div className="flex min-h-screen flex-col px-4 py-5 md:border-r md:border-line md:px-9 md:py-[26px]">
        <AuthBrand className="self-start" />
        <div className="mt-4 md:hidden">
          <ExampleBacktestStrip />
        </div>
        <main className="mx-auto grid w-full max-w-[340px] gap-3.5 pb-8 pt-7 md:my-auto md:py-8">
          <FormHeader title={title} subtitle={subtitle} />
          {children}
        </main>
        <footer className="hidden text-[12px] text-fg-3 md:block">
          Closed beta · invite only · paper and live trading on Alpaca
        </footer>
      </div>
      <aside className="auth-aside relative hidden flex-col items-center justify-center overflow-hidden px-8 py-12 md:flex lg:px-14">
        <AuthArt />
        <div className="auth-card relative w-full max-w-[680px] rounded-[14px] border bg-canvas p-7">
          <ExampleBacktestPanel />
        </div>
      </aside>
    </div>
  );
}
