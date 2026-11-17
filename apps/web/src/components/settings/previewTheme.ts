import type { CSSProperties } from 'react';

import type { DarkSurface, LightSurface } from '../../store/theme';
import { accentsFor, type ThemeMode } from '../../theme/accents';

type Triple = string;

interface Surface {
  canvas: Triple;
  panel: Triple;
  sunk: Triple;
  line: Triple;
  lineStrong: Triple;
  fg: Triple;
  fg2: Triple;
  fg3: Triple;
}

/** Surface tokens from styles/tokens.css, so the preview can show a mode that isn't applied. */
export const SURFACES: Record<DarkSurface | LightSurface, Surface> = {
  slate: {
    canvas: '15 19 22',
    panel: '21 26 31',
    sunk: '28 34 40',
    line: '37 44 52',
    lineStrong: '54 64 74',
    fg: '230 234 238',
    fg2: '170 179 189',
    fg3: '127 137 148',
  },
  black: {
    canvas: '10 10 10',
    panel: '17 17 17',
    sunk: '24 24 24',
    line: '34 34 34',
    lineStrong: '46 46 46',
    fg: '237 237 237',
    fg2: '163 163 163',
    fg3: '118 118 118',
  },
  warm: {
    canvas: '250 249 246',
    panel: '255 255 255',
    sunk: '242 240 234',
    line: '232 229 222',
    lineStrong: '207 203 194',
    fg: '21 25 31',
    fg2: '68 75 86',
    fg3: '107 113 124',
  },
  white: {
    canvas: '251 251 252',
    panel: '255 255 255',
    sunk: '244 245 247',
    line: '236 238 241',
    lineStrong: '220 223 227',
    fg: '17 20 24',
    fg2: '71 77 86',
    fg3: '107 113 122',
  },
};

/** Dark accents whose text colour differs from the swatch, which shows the button fill. */
const DARK_TEXT_ACCENT: Readonly<Record<string, Triple>> = {
  blue: '91 140 255',
  slate: '143 164 207',
};

export function hexTriple(hex: string): Triple {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? [...h].map((c) => c + c).join('') : h, 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
}

export function accentTriple(mode: ThemeMode, key: string): Triple {
  if (mode === 'dark' && DARK_TEXT_ACCENT[key]) return DARK_TEXT_ACCENT[key];
  const accent = accentsFor(mode).find((a) => a.key === key) ?? accentsFor(mode)[0];
  return hexTriple(accent.swatch);
}

/** The custom properties that repaint everything inside the preview in another theme. */
export function previewVars(
  mode: ThemeMode,
  surface: DarkSurface | LightSurface,
  accent: string
): CSSProperties {
  const s = SURFACES[surface];
  const vars: Record<string, string> = {
    '--canvas': s.canvas,
    '--panel': s.panel,
    '--sunk': s.sunk,
    '--line': s.line,
    '--line-strong': s.lineStrong,
    '--fg': s.fg,
    '--fg-2': s.fg2,
    '--fg-3': s.fg3,
    '--accent': accentTriple(mode, accent),
    colorScheme: mode,
  };
  return vars as CSSProperties;
}

export function accentLabel(mode: ThemeMode, key: string): string {
  return accentsFor(mode).find((a) => a.key === key)?.label ?? '';
}
