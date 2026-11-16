const STEP: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };

/** Where an arrow, Home or End key moves focus in a radio group of `count`, or null for other keys. */
export function radioKeyTarget(key: string, index: number, count: number): number | null {
  if (count <= 0) return null;
  if (key === 'Home') return 0;
  if (key === 'End') return count - 1;
  const step = STEP[key];
  return step === undefined ? null : (index + step + count) % count;
}
