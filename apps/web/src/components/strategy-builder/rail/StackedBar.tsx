export interface BarSegment {
  key: string;
  pct: number;
  fill: string;
}

/** Holdings side by side in one bar, each as wide as its weight. */
export function StackedBar({
  segments,
  height = 8,
  label,
}: {
  segments: readonly BarSegment[];
  height?: number;
  label: string;
}) {
  const visible = segments.filter((s) => s.pct > 0);
  if (visible.length === 0) return null;
  return (
    <div role="img" aria-label={label} className="flex gap-0.5" style={{ height }}>
      {visible.map((s) => (
        <span
          key={s.key}
          className="block h-full rounded-[1px]"
          style={{ width: `calc(${s.pct}% - 2px)`, background: s.fill }}
        />
      ))}
    </div>
  );
}
