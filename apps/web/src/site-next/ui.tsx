import { Moon, Sun } from 'lucide-react';
import type { ReactNode } from 'react';

import { AuthArt } from '../components/auth/AuthArt';
import { useResolvedTheme, useThemeStore } from '../store/theme';

export const WRAP = 'mx-auto w-full max-w-[1320px] px-4 md:px-10';

/** The sign-in screen's candle-chart art, filling its positioned parent. */
export function ArtBackdrop({ className = '' }: { className?: string }) {
  return (
    <div aria-hidden="true" className={`auth-aside absolute inset-0 overflow-hidden ${className}`}>
      <AuthArt />
    </div>
  );
}

/** One crisp bordered panel, as on the sign-in screen. */
export function Card({
  children,
  className = '',
  plain = false,
}: {
  children: ReactNode;
  className?: string;
  /** A bordered panel without the sign-in rim light, for cards that are not over the art. */
  plain?: boolean;
}) {
  const look = plain ? 'border-line-strong shadow-sm' : 'auth-card';
  return (
    <div className={`${look} relative rounded-[14px] border bg-canvas ${className}`}>
      {children}
    </div>
  );
}

export function Kicker({ children }: { children: ReactNode }) {
  return (
    <span className="font-mono text-[11.5px] uppercase tracking-[0.14em] text-fg-3">
      {children}
    </span>
  );
}

export function SectionHead({
  kicker,
  title,
  lede,
}: {
  kicker: string;
  title: string;
  lede?: string;
}) {
  return (
    <div className="grid content-start gap-3">
      <Kicker>{kicker}</Kicker>
      <h2 className="m-0 max-w-[720px] text-[30px] font-semibold leading-[1.1] tracking-[-0.03em] md:text-[40px]">
        {title}
      </h2>
      {lede && <p className="m-0 max-w-[560px] text-[16px] leading-relaxed text-fg-2">{lede}</p>}
    </div>
  );
}

export function ModeToggle() {
  const { mode } = useResolvedTheme();
  const setMode = useThemeStore((s) => s.setMode);
  const next = mode === 'dark' ? 'light' : 'dark';
  const Icon = mode === 'dark' ? Moon : Sun;
  return (
    <button
      type="button"
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
      onClick={() => setMode(next)}
      className="grid h-8 w-8 flex-none place-items-center rounded-full border border-line text-fg-2 transition-colors hover:border-line-strong hover:text-fg"
    >
      <Icon size={14} strokeWidth={1.75} aria-hidden="true" />
    </button>
  );
}
