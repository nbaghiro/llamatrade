export interface LogoProps {
  /** Square size of the brand mark in px. Defaults to 32. */
  size?: number;
  /** Render the "LlamaTrade" wordmark beside the mark. Defaults to false. */
  showText?: boolean;
}

/**
 * Logo — the Monolith brand mark: ink box, orange frame, LT monogram.
 * Optionally followed by the "LlamaTrade" display wordmark.
 */
export function Logo({ size = 32, showText = false }: LogoProps) {
  const glyph = Math.round(size * 0.72);

  return (
    <div className="flex items-center gap-2.5">
      {/* Monolith brand mark: ink box, orange frame, LT monogram */}
      <div
        className="flex-shrink-0 grid place-items-center bg-ink border-[3px] border-orange-500"
        style={{ width: size, height: size }}
      >
        <svg width={glyph} height={glyph} viewBox="0 0 120 120" fill="none" aria-hidden="true">
          {/* L — bone (CSS fill reads the token; SVG fill attrs don't resolve var()) */}
          <g style={{ fill: 'rgb(var(--lt-bone))' }}>
            <rect x="30" y="26" width="17" height="52" />
            <rect x="30" y="61" width="39" height="17" />
          </g>
          {/* T — signal orange */}
          <rect x="54" y="26" width="40" height="17" fill="#ff4d1c" />
          <rect x="68" y="26" width="17" height="52" fill="#ff4d1c" />
        </svg>
      </div>

      {showText && (
        <span className="font-display text-lg uppercase tracking-tight leading-none text-ink">
          LlamaTrade
        </span>
      )}
    </div>
  );
}
