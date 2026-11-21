/**
 * B Session colour tokens for React Native, mirroring apps/web/src/styles/tokens.css
 * and apps/web/src/theme/accents.ts. Pure data and functions with no imports, so the
 * resolution logic runs under `node --test` as well as in the app.
 */

export type ThemeMode = 'light' | 'dark';
export type ModePreference = 'system' | ThemeMode;
export type DarkSurface = 'black' | 'slate';
export type LightSurface = 'white' | 'warm';

export interface AppearancePrefs {
  mode: ModePreference;
  darkSurface: DarkSurface;
  lightSurface: LightSurface;
  darkAccent: string;
  lightAccent: string;
}

export interface Colors {
  canvas: string;
  panel: string;
  sunk: string;
  line: string;
  lineStrong: string;
  fg: string;
  fg2: string;
  fg3: string;
  chart: readonly [string, string, string, string, string];
  grid: string;
  gain: string;
  loss: string;
  risk: string;
  riskSoft: string;
  riskLine: string;
  /** Text, icons and selection. */
  accent: string;
  /** Primary button and send-button fill; deeper than `accent` for Blue and Slate blue in dark. */
  accentFill: string;
  /** Text on `accentFill`. */
  accentInk: string;
  accentSoft: string;
  scrim: string;
}

export interface Accent {
  key: string;
  label: string;
  /** Picker dot colour: the fill where it differs from the text accent. */
  swatch: string;
}

type Surface = Omit<
  Colors,
  | 'accent'
  | 'accentFill'
  | 'accentInk'
  | 'accentSoft'
  | 'gain'
  | 'loss'
  | 'risk'
  | 'riskSoft'
  | 'riskLine'
  | 'scrim'
>;

const DARK_SURFACES: Record<DarkSurface, Surface> = {
  black: {
    canvas: '#0a0a0a',
    panel: '#111111',
    sunk: '#181818',
    line: '#222222',
    lineStrong: '#2e2e2e',
    fg: '#ededed',
    fg2: '#a3a3a3',
    fg3: '#767676',
    chart: ['#ededed', '#a3a3a3', '#767676', '#4d4d4d', '#2e2e2e'],
    grid: '#242424',
  },
  slate: {
    canvas: '#0f1316',
    panel: '#151a1f',
    sunk: '#1c2228',
    line: '#252c34',
    lineStrong: '#36404a',
    fg: '#e6eaee',
    fg2: '#aab3bd',
    fg3: '#7f8994',
    chart: ['#e6eaee', '#aab3bd', '#7f8994', '#56606b', '#363f48'],
    grid: '#252c34',
  },
};

const LIGHT_SURFACES: Record<LightSurface, Surface> = {
  white: {
    canvas: '#fbfbfc',
    panel: '#ffffff',
    sunk: '#f4f5f7',
    line: '#eceef1',
    lineStrong: '#dcdfe3',
    fg: '#111418',
    fg2: '#474d56',
    fg3: '#6b717a',
    chart: ['#23272d', '#50565f', '#858b94', '#b5b9bf', '#dde0e4'],
    grid: '#eef0f2',
  },
  warm: {
    canvas: '#faf9f6',
    panel: '#ffffff',
    sunk: '#f2f0ea',
    line: '#e8e5de',
    lineStrong: '#cfcbc2',
    fg: '#15191f',
    fg2: '#444b56',
    fg3: '#6b717c',
    chart: ['#2a2f37', '#545b66', '#878d97', '#b6bac1', '#dcdee2'],
    grid: '#ece9e2',
  },
};

/** The calm, desaturated gain/loss pair the web uses (tokens.css --gain/--loss). */
const DARK_STATUS = {
  gain: '#79b394',
  loss: '#d48b84',
  risk: '#f0a63a',
  riskSoft: 'rgba(240,166,58,0.1)',
  riskLine: 'rgba(240,166,58,0.45)',
  scrim: 'rgba(0,0,0,0.55)',
} as const;

const LIGHT_STATUS = {
  gain: '#3f7a5c',
  loss: '#a5544d',
  risk: '#8a5a00',
  riskSoft: '#fbf3e2',
  riskLine: '#e7cf9d',
  scrim: 'rgba(21,25,31,0.32)',
} as const;

interface DarkAccentSpec extends Accent {
  fill?: string;
  ink: string;
  softAlpha?: number;
}

const DARK_ACCENT_SPECS: readonly DarkAccentSpec[] = [
  { key: 'silver', label: 'Silver', swatch: '#a1a1aa', ink: '#0a0a0a' },
  {
    key: 'white',
    label: 'Frost',
    swatch: '#dbe3f0',
    ink: '#0b1220',
    softAlpha: 0.12,
  },
  { key: 'orange', label: 'Orange', swatch: '#ff9f43', ink: '#1f1000' },
  { key: 'lime', label: 'Lime', swatch: '#d9f05c', ink: '#141a00' },
  { key: 'teal', label: 'Teal', swatch: '#2dd4bf', ink: '#031a17' },
  {
    key: 'cyan',
    label: 'Cyan',
    swatch: '#4cc2ff',
    ink: '#04121c',
    softAlpha: 0.14,
  },
  {
    key: 'blue',
    label: 'Blue',
    swatch: '#2563eb',
    ink: '#ffffff',
    fill: '#2563eb',
  },
  {
    key: 'slate',
    label: 'Slate blue',
    swatch: '#475f8a',
    ink: '#ffffff',
    fill: '#475f8a',
  },
  { key: 'indigo', label: 'Indigo', swatch: '#818cf8', ink: '#0b0b2e' },
  { key: 'violet', label: 'Violet', swatch: '#a78bfa', ink: '#14082e' },
  { key: 'lilac', label: 'Lilac', swatch: '#d8b4fe', ink: '#1e0b33' },
  { key: 'pink', label: 'Pink', swatch: '#f472b6', ink: '#2b0618' },
];

/** Dark text accents where they differ from the swatch (Blue and Slate blue swatch the fill). */
const DARK_TEXT_ACCENT: Readonly<Record<string, string>> = {
  blue: '#5b8cff',
  slate: '#8fa4cf',
};

export const DARK_ACCENTS: readonly Accent[] = DARK_ACCENT_SPECS.map(({ key, label, swatch }) => ({
  key,
  label,
  swatch,
}));

export const LIGHT_ACCENTS: readonly Accent[] = [
  { key: 'charcoal', label: 'Charcoal', swatch: '#3a3f47' },
  { key: 'ink', label: 'Midnight', swatch: '#1b2940' },
  { key: 'rust', label: 'Rust', swatch: '#a8520a' },
  { key: 'pine', label: 'Pine', swatch: '#1d5c45' },
  { key: 'teal', label: 'Teal', swatch: '#0f6b78' },
  { key: 'ocean', label: 'Ocean', swatch: '#1d4e89' },
  { key: 'blue', label: 'Blue', swatch: '#2563eb' },
  { key: 'navy', label: 'Navy', swatch: '#1f3b73' },
  { key: 'slate', label: 'Slate blue', swatch: '#475f8a' },
  { key: 'iris', label: 'Iris', swatch: '#4a3fd4' },
  { key: 'plum', label: 'Plum', swatch: '#6b2d5c' },
  { key: 'burgundy', label: 'Burgundy', swatch: '#5a1e3c' },
];

export const DEFAULT_APPEARANCE: AppearancePrefs = {
  mode: 'system',
  darkSurface: 'slate',
  lightSurface: 'white',
  darkAccent: 'slate',
  lightAccent: 'ocean',
};

export function accentsFor(mode: ThemeMode): readonly Accent[] {
  return mode === 'dark' ? DARK_ACCENTS : LIGHT_ACCENTS;
}

export function isAccentFor(mode: ThemeMode, key: unknown): key is string {
  return typeof key === 'string' && accentsFor(mode).some((a) => a.key === key);
}

function rgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** `#rrggbb` at an alpha, as an rgba() string. */
export function withAlpha(hex: string, alpha: number): string {
  const [r, g, b] = rgb(hex);
  return `rgba(${r},${g},${b},${alpha})`;
}

/** `#rrggbb` mixed `amount` of the way from white, like color-mix(in srgb, c amount, #fff). */
export function mixWithWhite(hex: string, amount: number): string {
  const channel = (c: number) =>
    Math.round(c * amount + 255 * (1 - amount))
      .toString(16)
      .padStart(2, '0');
  return `#${rgb(hex).map(channel).join('')}`;
}

function pick<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.find((a) => a === value) ?? fallback;
}

/** Coerces anything read from storage into valid preferences, field by field. */
export function sanitizeAppearance(raw: unknown): AppearancePrefs {
  const r: Record<string, unknown> = typeof raw === 'object' && raw !== null ? { ...raw } : {};
  const d = DEFAULT_APPEARANCE;
  return {
    mode: pick(r.mode, ['system', 'light', 'dark'] as const, d.mode),
    darkSurface: pick(r.darkSurface, ['black', 'slate'] as const, d.darkSurface),
    lightSurface: pick(r.lightSurface, ['white', 'warm'] as const, d.lightSurface),
    darkAccent: isAccentFor('dark', r.darkAccent) ? r.darkAccent : d.darkAccent,
    lightAccent: isAccentFor('light', r.lightAccent) ? r.lightAccent : d.lightAccent,
  };
}

/** The mode that renders: the explicit choice, or the device scheme in System (dark when unknown). */
export function resolveMode(pref: ModePreference, system: string | null | undefined): ThemeMode {
  if (pref !== 'system') return pref;
  return system === 'light' ? 'light' : 'dark';
}

function darkAccentColors(key: string) {
  const spec =
    DARK_ACCENT_SPECS.find((a) => a.key === key) ??
    DARK_ACCENT_SPECS.find((a) => a.key === DEFAULT_APPEARANCE.darkAccent) ??
    DARK_ACCENT_SPECS[0];
  const accent = DARK_TEXT_ACCENT[spec.key] ?? spec.swatch;
  return {
    accent,
    accentFill: spec.fill ?? accent,
    accentInk: spec.ink,
    accentSoft: withAlpha(accent, spec.softAlpha ?? 0.16),
  };
}

function lightAccentColors(key: string) {
  const accent = (
    LIGHT_ACCENTS.find((a) => a.key === key) ??
    LIGHT_ACCENTS.find((a) => a.key === DEFAULT_APPEARANCE.lightAccent) ??
    LIGHT_ACCENTS[0]
  ).swatch;
  return {
    accent,
    accentFill: accent,
    accentInk: '#ffffff',
    accentSoft: mixWithWhite(accent, 0.1),
  };
}

export function colorsFor(prefs: AppearancePrefs, mode: ThemeMode): Colors {
  return mode === 'dark'
    ? {
        ...DARK_SURFACES[prefs.darkSurface],
        ...DARK_STATUS,
        ...darkAccentColors(prefs.darkAccent),
      }
    : {
        ...LIGHT_SURFACES[prefs.lightSurface],
        ...LIGHT_STATUS,
        ...lightAccentColors(prefs.lightAccent),
      };
}

/** Background candle art: drawn in the accent, faint, with a soft glow from one side. */
export interface ArtTokens {
  color: string;
  /** Candle opacity at full intensity. */
  opacity: number;
  glow: string;
  glowOpacity: number;
}

export function artFor(colors: Pick<Colors, 'accent'>, mode: ThemeMode): ArtTokens {
  return mode === 'dark'
    ? { color: colors.accent, opacity: 0.24, glow: colors.accent, glowOpacity: 0.2 }
    : { color: colors.accent, opacity: 0.17, glow: colors.accent, glowOpacity: 0.12 };
}
