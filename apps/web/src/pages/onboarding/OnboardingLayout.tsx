import { useEffect, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { Logo } from '../../components/common/Logo';
import { useAuthStore } from '../../store/auth';
import { useOnboardingStore } from '../../store/onboarding';

const STEPS = 3;

function Bars({ step, className }: { step: number; className: string }) {
  return (
    <span className={className} aria-hidden="true">
      {Array.from({ length: STEPS }, (_, i) => (
        <i
          key={i}
          className={`block h-1 flex-1 rounded-[2px] md:w-12 md:flex-none ${i < step ? 'bg-accent' : 'bg-sunk'}`}
        />
      ))}
    </span>
  );
}

interface OnboardingLayoutProps {
  step: 1 | 2 | 3;
  children: ReactNode;
}

/** Brand, progress and an always-visible Skip above one focused onboarding screen. */
export function OnboardingLayout({ step, children }: OnboardingLayoutProps) {
  const userId = useAuthStore((s) => s.user?.id ?? '');
  const markWelcomeSeen = useOnboardingStore((s) => s.markWelcomeSeen);

  useEffect(() => {
    markWelcomeSeen(userId);
  }, [markWelcomeSeen, userId]);

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <header className="flex h-14 flex-none items-center justify-between gap-4 border-b border-line px-4 md:px-[26px]">
        <span className="hidden md:inline-flex">
          <Logo size={22} showText />
        </span>
        <span className="flex items-center gap-1.5 text-[12.5px] md:text-[12px]">
          <span className="num mr-1.5 text-fg-3">
            Step {step} of {STEPS}
          </span>
          <Bars step={step} className="hidden gap-1.5 md:flex" />
        </span>
        <Link to="/dashboard" className="text-[14px] text-fg-2 hover:text-fg md:text-[13px]">
          <span className="md:hidden">Skip</span>
          <span className="hidden md:inline">Skip to Home</span>
        </Link>
      </header>
      <Bars step={step} className="flex gap-1.5 px-4 pt-3 md:hidden" />
      <main className="grid flex-1 grid-cols-[minmax(0,1fr)] content-start justify-items-center gap-[18px] px-4 py-6 md:content-center md:px-[60px] md:py-8">
        {children}
      </main>
    </div>
  );
}

export function StepTitle({ title, lead }: { title: string; lead?: string }) {
  return (
    <div className="grid w-full max-w-[640px] gap-2 md:justify-items-center md:text-center">
      <h1 className="m-0 text-[27px] font-semibold leading-[1.15] tracking-[-0.02em] md:text-[26px]">
        {title}
      </h1>
      {lead && <p className="m-0 max-w-[560px] text-[14.5px] text-fg-2 md:text-[13.5px]">{lead}</p>}
    </div>
  );
}
