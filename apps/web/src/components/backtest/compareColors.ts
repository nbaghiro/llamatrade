/** Line colours in run order; the benchmark is drawn dashed in fg-3. */
export const COMPARE_COLORS = [
  'rgb(var(--accent))',
  'rgb(var(--chart-2))',
  'rgb(var(--chart-4))',
  'rgb(var(--chart-3))',
  'rgb(var(--chart-5))',
] as const;

export const compareColor = (i: number) => COMPARE_COLORS[i % COMPARE_COLORS.length];
