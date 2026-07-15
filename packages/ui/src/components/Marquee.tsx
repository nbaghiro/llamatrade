import type { CSSProperties, ReactNode } from 'react';

export interface MarqueeProps {
  /** Ticker items rendered in order, then seamlessly duplicated for the loop. */
  items: string[];
  /** Full-loop duration in seconds. Defaults to 28. */
  speed?: number;
  /** Node rendered before each item (defaults to the orange Monolith asterisk). */
  separator?: ReactNode;
  /** Classes for the outer (clipping) container. */
  className?: string;
  /** Classes for the moving track — use for color/opacity (e.g. `text-bone/45`). */
  trackClassName?: string;
}

const DEFAULT_SEPARATOR = (
  <span className="mx-4 text-orange-500" aria-hidden="true">
    ✱
  </span>
);

/**
 * Marquee — a prop-driven horizontal ticker in the Monolith style
 * (mono, uppercase, tracked). Items are duplicated so the CSS translate loop is
 * seamless. Respects `prefers-reduced-motion` (the track holds still).
 *
 * The keyframes are injected via a component-scoped `<style>`; duplicate
 * identical keyframes across multiple instances are harmless.
 */
export function Marquee({
  items,
  speed = 28,
  separator = DEFAULT_SEPARATOR,
  className = '',
  trackClassName = '',
}: MarqueeProps) {
  const doubled = [...items, ...items];
  const trackStyle = { '--lt-marquee-speed': `${speed}s` } as CSSProperties;

  return (
    <div className={`overflow-hidden ${className}`.trim()}>
      <style>{`
        @keyframes lt-marquee { from { transform: translateX(0); } to { transform: translateX(-50%); } }
        .lt-marquee-track { animation: lt-marquee var(--lt-marquee-speed, 28s) linear infinite; }
        @media (prefers-reduced-motion: reduce) { .lt-marquee-track { animation: none; } }
      `}</style>
      <div
        className={`lt-marquee-track flex w-max whitespace-nowrap font-mono text-[11px] font-bold uppercase tracking-wider ${trackClassName}`.trim()}
        style={trackStyle}
      >
        {doubled.map((item, i) => (
          <span key={i} className="flex items-center">
            {separator}
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}
