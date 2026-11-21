import { useEffect, useRef, useState } from 'react';

import { INDICATORS } from '../marketing/data/illustrative';
import { useResolvedTheme } from '../store/theme';

import { HeroInvite } from './listState';
import { ArtBackdrop, Card, Kicker, WRAP } from './ui';

/** What the demo shows, with the second at which each part starts. The clip loops at about 31 s. */
const STEPS: readonly { label: string; short: string; from: number }[] = [
  { label: 'Describe the strategy', short: 'Describe', from: 0 },
  { label: 'Backtest against SPY', short: 'Backtest', from: 13 },
  { label: 'Start on paper', short: 'Paper', from: 24.5 },
];
const LOOP_BACK = 27;

const FACTS: readonly [string, string][] = [
  [String(INDICATORS.length), 'indicators in the language'],
  ['3', 'ways to build a strategy'],
  ['~80', 'templates to start from'],
  ['$0', 'while sign-up is by invite'],
];

function stepAt(t: number): number {
  if (t >= LOOP_BACK) return 0;
  let i = 0;
  STEPS.forEach((s, k) => {
    if (t >= s.from) i = k;
  });
  return i;
}

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  );
  useEffect(() => {
    const q = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!q) return;
    const on = (e: MediaQueryListEvent) => setReduced(e.matches);
    q.addEventListener('change', on);
    return () => q.removeEventListener('change', on);
  }, []);
  return reduced;
}

function DemoCard() {
  const { mode } = useResolvedTheme();
  const reduced = useReducedMotion();
  const video = useRef<HTMLVideoElement>(null);
  const [step, setStep] = useState(0);
  const src = `/site-next/demo-${mode}`;

  const seek = (i: number) => {
    const v = video.current;
    if (!v) return;
    v.currentTime = STEPS[i].from + 0.05;
    setStep(i);
  };

  return (
    <Card className="overflow-hidden p-1.5 md:p-2">
      <div className="relative aspect-[16/10] overflow-hidden rounded-[9px] border border-line bg-panel">
        <video
          key={src}
          ref={video}
          className="block h-full w-full object-cover"
          poster={`${src}.jpg`}
          autoPlay={!reduced}
          controls={reduced}
          muted
          loop
          playsInline
          preload="auto"
          aria-label="Demo: a strategy described to the copilot, backtested against SPY, then started on paper"
          onTimeUpdate={(e) => setStep(stepAt(e.currentTarget.currentTime))}
        >
          <source src={`${src}.mp4`} type="video/mp4" />
        </video>
      </div>
      <ol className="m-0 grid list-none grid-cols-3 p-0">
        {STEPS.map((s, i) => (
          <li key={s.label} className="min-w-0">
            <button
              type="button"
              onClick={() => seek(i)}
              aria-current={i === step ? 'step' : undefined}
              className={`grid w-full gap-1.5 px-2 pb-2 pt-3 text-left transition-colors md:px-3 ${
                i === step ? 'text-fg' : 'text-fg-3 hover:text-fg-2'
              }`}
            >
              <span
                aria-hidden="true"
                className={`h-px w-full ${i === step ? 'bg-fg' : 'bg-line-strong'}`}
              />
              <span className="flex items-baseline gap-2 truncate text-[12px] md:text-[13px]">
                <span className="font-mono text-[11px] tabular-nums text-fg-3">0{i + 1}</span>
                <span className="truncate sm:hidden">{s.short}</span>
                <span className="hidden truncate sm:inline">{s.label}</span>
              </span>
            </button>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export function Hero() {
  return (
    <section id="top" className="sn-art-fade relative overflow-hidden">
      <ArtBackdrop />
      <div
        className={`${WRAP} relative grid grid-cols-1 justify-items-center pb-16 pt-16 text-center md:pt-24`}
      >
        <Kicker>Invite only · paper and live trading</Kicker>
        <h1 className="m-0 mt-5 max-w-[880px] text-[40px] font-semibold leading-[1.02] tracking-[-0.04em] sm:text-[56px] md:text-[68px]">
          Algorithmic trading on your own account.
        </h1>
        <p className="m-0 mt-5 max-w-[540px] text-[17px] leading-relaxed text-fg-2">
          Build a strategy, backtest it, then run it on Alpaca, in paper or live.
        </p>
        <HeroInvite />
        <div id="demo" className="mt-8 w-full max-w-[1080px] scroll-mt-24 text-left">
          <DemoCard />
        </div>
        <dl className="m-0 mt-10 grid w-full max-w-[1080px] grid-cols-2 border-y border-line text-left md:grid-cols-4">
          {FACTS.map(([n, label], i) => (
            <div
              key={label}
              className={`grid gap-1 px-4 py-4 ${i % 2 ? 'border-l border-line' : ''} ${
                i >= 2 ? 'border-t border-line md:border-t-0' : ''
              } ${i === 2 ? 'md:border-l' : ''}`}
            >
              <dt className="order-2 text-[12.5px] text-fg-3">{label}</dt>
              <dd className="order-1 m-0 font-mono text-[22px] tabular-nums tracking-[-0.02em]">
                {n}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
