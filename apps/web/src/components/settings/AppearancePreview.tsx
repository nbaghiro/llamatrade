import type { DarkSurface, LightSurface } from '../../store/theme';
import type { ThemeMode } from '../../theme/accents';
import { LogoMark } from '../common/Logo';

import { previewVars } from './previewTheme';

const CURVE =
  'M0 70 C 30 66, 50 58, 80 60 S 130 44, 160 48 S 210 30, 240 36 S 290 22, 320 26 S 370 12, 400 14';
const BENCH = 'M0 72 C 40 68, 80 62, 120 58 S 200 46, 240 44 S 320 34, 400 28';

/**
 * A small static Home (the annotated curve with session lanes) painted in a chosen surface and
 * accent. It shows shapes, not figures, so it never shows a number that isn't yours.
 */
export function AppearancePreview({
  mode,
  surface,
  accent,
  lanes,
  compact = false,
}: {
  mode: ThemeMode;
  surface: DarkSurface | LightSurface;
  accent: string;
  lanes: readonly string[];
  compact?: boolean;
}) {
  const names = lanes.length ? lanes.slice(0, compact ? 2 : 4) : ['Your first session'];
  return (
    <div
      aria-label={`Preview of Home in ${mode} mode`}
      role="img"
      style={previewVars(mode, surface, accent)}
      className="overflow-hidden rounded-[10px] border border-line bg-canvas text-fg shadow-lg"
    >
      <div className="flex items-center gap-2.5 border-b border-line bg-panel px-3 py-2">
        <LogoMark size={compact ? 14 : 18} />
        {!compact && (
          <span className="text-[9.5px] font-semibold uppercase tracking-[0.16em]">LlamaTrade</span>
        )}
        <span className="ml-auto flex gap-1.5" aria-hidden="true">
          <i className="h-1.5 w-8 rounded-full bg-accent" />
          <i className="h-1.5 w-8 rounded-full bg-line-strong" />
          <i className="h-1.5 w-8 rounded-full bg-line-strong" />
        </span>
      </div>
      <div className="grid gap-2.5 p-3.5">
        {!compact && <span className="text-[11px] text-fg-3">Home</span>}
        <div className="grid gap-1">
          <span className="text-[9px] font-medium uppercase tracking-[0.08em] text-fg-3">
            Total equity
          </span>
          <i className="block h-3.5 w-36 rounded-[3px] bg-fg/80" aria-hidden="true" />
        </div>
        {!compact && (
          <div className="flex items-center gap-2 text-[10px] text-fg-2">
            <span className="rounded-full border border-line-strong px-2 py-0.5">
              {names[0]} started
            </span>
            <span className="ml-auto rounded-full bg-accent px-2 py-0.5 font-semibold text-canvas">
              Fills today
            </span>
          </div>
        )}
        <svg viewBox="0 0 400 80" className="h-auto w-full" aria-hidden="true">
          <defs>
            <linearGradient id={`pv-${mode}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="rgb(var(--accent))" stopOpacity="0.25" />
              <stop offset="1" stopColor="rgb(var(--accent))" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={`${CURVE} L400 80 L0 80 Z`} fill={`url(#pv-${mode})`} />
          <path
            d={BENCH}
            fill="none"
            stroke="rgb(var(--fg-3))"
            strokeWidth="1.2"
            strokeDasharray="3 3"
          />
          <path d={CURVE} fill="none" stroke="rgb(var(--accent))" strokeWidth="2" />
          <line x1="330" x2="330" y1="0" y2="80" stroke="rgb(var(--fg))" strokeWidth="1" />
        </svg>
        <div className="grid gap-1.5">
          {names.map((n, i) => (
            <div key={n} className="flex items-center gap-2.5 text-[10.5px] text-fg-2">
              <span className="w-[42%] truncate">{n}</span>
              <span className="relative h-px flex-1 bg-line-strong">
                {[0.2, 0.5, 0.78].map((x) => (
                  <i
                    key={x}
                    className="absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border-[1.5px] border-accent bg-canvas"
                    style={{ left: `${(x + i * 0.07) * 100}%` }}
                  />
                ))}
              </span>
            </div>
          ))}
        </div>
        {!compact && (
          <div className="flex items-center gap-2.5 pt-1 text-[10px] text-fg-3">
            <span className="rounded-[5px] bg-fg px-2.5 py-1 font-semibold text-canvas">
              New strategy
            </span>
            Buttons stay ink in every accent
          </div>
        )}
      </div>
    </div>
  );
}
