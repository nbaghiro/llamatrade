export type ThemeMode = 'light' | 'dark';

export interface Accent {
  key: string;
  label: string;
  /** Colour of the picker dot: the fill colour where it differs from the text accent. */
  swatch: string;
  mode: ThemeMode;
}

export const DARK_ACCENTS: readonly Accent[] = [
  { key: 'silver', label: 'Silver', swatch: '#a1a1aa', mode: 'dark' },
  { key: 'white', label: 'Frost', swatch: '#dbe3f0', mode: 'dark' },
  { key: 'orange', label: 'Orange', swatch: '#ff9f43', mode: 'dark' },
  { key: 'lime', label: 'Lime', swatch: '#d9f05c', mode: 'dark' },
  { key: 'teal', label: 'Teal', swatch: '#2dd4bf', mode: 'dark' },
  { key: 'cyan', label: 'Cyan', swatch: '#4cc2ff', mode: 'dark' },
  { key: 'blue', label: 'Blue', swatch: '#2563eb', mode: 'dark' },
  { key: 'slate', label: 'Slate blue', swatch: '#475f8a', mode: 'dark' },
  { key: 'indigo', label: 'Indigo', swatch: '#818cf8', mode: 'dark' },
  { key: 'violet', label: 'Violet', swatch: '#a78bfa', mode: 'dark' },
  { key: 'lilac', label: 'Lilac', swatch: '#d8b4fe', mode: 'dark' },
  { key: 'pink', label: 'Pink', swatch: '#f472b6', mode: 'dark' },
];

export const LIGHT_ACCENTS: readonly Accent[] = [
  { key: 'charcoal', label: 'Charcoal', swatch: '#3a3f47', mode: 'light' },
  { key: 'ink', label: 'Midnight', swatch: '#1b2940', mode: 'light' },
  { key: 'rust', label: 'Rust', swatch: '#a8520a', mode: 'light' },
  { key: 'pine', label: 'Pine', swatch: '#1d5c45', mode: 'light' },
  { key: 'teal', label: 'Teal', swatch: '#0f6b78', mode: 'light' },
  { key: 'ocean', label: 'Ocean', swatch: '#1d4e89', mode: 'light' },
  { key: 'blue', label: 'Blue', swatch: '#2563eb', mode: 'light' },
  { key: 'navy', label: 'Navy', swatch: '#1f3b73', mode: 'light' },
  { key: 'slate', label: 'Slate blue', swatch: '#475f8a', mode: 'light' },
  { key: 'iris', label: 'Iris', swatch: '#4a3fd4', mode: 'light' },
  { key: 'plum', label: 'Plum', swatch: '#6b2d5c', mode: 'light' },
  { key: 'burgundy', label: 'Burgundy', swatch: '#5a1e3c', mode: 'light' },
];

export const ACCENTS: readonly Accent[] = [...DARK_ACCENTS, ...LIGHT_ACCENTS];

export const DEFAULT_ACCENT: Record<ThemeMode, string> = { dark: 'slate', light: 'ocean' };

export function accentsFor(mode: ThemeMode): readonly Accent[] {
  return mode === 'dark' ? DARK_ACCENTS : LIGHT_ACCENTS;
}

export function isAccentFor(mode: ThemeMode, key: unknown): key is string {
  return typeof key === 'string' && accentsFor(mode).some((a) => a.key === key);
}
