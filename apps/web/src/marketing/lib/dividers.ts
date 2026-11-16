/** Price-axis section dividers: a numbered label and a rule with ticks, like a chart's x-axis. */

export const AXIS_TICK_STEP = 48;
export const AXIS_HEIGHT = 9;
export const AXIS_TICK_HEIGHT = 5;

/** "01 build", "02 backtest"…, numbered in page order. */
export function dividerLabels(names: readonly string[]): string[] {
  const width = Math.max(2, String(names.length).length);
  return names.map((n, i) => `${String(i + 1).padStart(width, '0')} ${n.trim().toLowerCase()}`);
}

/** x of each tick on a rule `width` wide: one at 0 and every `step` px after, inside the rule. */
export function axisTicks(width: number, step = AXIS_TICK_STEP): number[] {
  if (width < 1 || step <= 0) return [];
  const out: number[] = [];
  for (let x = 0; x <= width - 1; x += step) out.push(x);
  return out;
}
