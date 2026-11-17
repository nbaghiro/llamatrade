import type { BarPart } from './placement';

/** The paper account as one bar: sleeves in their colours, unallocated cash last. */
export function PaperBar({
  parts,
  colorOf,
  label,
}: {
  parts: readonly BarPart[];
  colorOf: (id: string) => string;
  label: string;
}) {
  const total = parts.reduce((s, p) => s + Math.max(0, p.value), 0);
  return (
    <div
      role="img"
      aria-label={label}
      className="flex h-2.5 w-full gap-[2px] overflow-hidden rounded-[3px]"
    >
      {parts
        .filter((p) => p.value > 0)
        .map((p) => {
          const base = p.id.replace(/\+$/, '');
          const color = colorOf(base);
          const style = p.added
            ? {
                flexGrow: p.value,
                backgroundImage: `repeating-linear-gradient(135deg, ${color} 0 2px, transparent 2px 5px)`,
                boxShadow: `inset 0 0 0 1px ${color}`,
              }
            : { flexGrow: p.value, background: color };
          return (
            <i
              key={p.id}
              className="block h-full min-w-[3px] basis-0"
              style={total > 0 ? style : { flexGrow: 1 }}
            />
          );
        })}
    </div>
  );
}
