import { dividerLabels } from '../lib/dividers';

/** Sections with a price-axis divider, in page order. The divider stands in for each kicker. */
const NAMES = {
  film: 'the app',
  build: 'build',
  backtest: 'backtest',
  copilot: 'copilot',
  live: 'sessions',
  own: 'your account',
  join: 'closed beta · invite only',
} as const;

export type SectionKey = keyof typeof NAMES;

const KEYS = Object.keys(NAMES) as SectionKey[];
const LABELS = dividerLabels(KEYS.map((k) => NAMES[k]));

export const DIVIDER: Record<SectionKey, string> = Object.fromEntries(
  KEYS.map((k, i) => [k, LABELS[i]])
) as Record<SectionKey, string>;
