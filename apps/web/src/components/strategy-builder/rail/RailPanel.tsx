import type { ReactNode } from 'react';

export function RailPanel({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <header className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-3">
        <h4 className="m-0 text-[13px] font-semibold text-fg">{title}</h4>
        {meta && <span className="text-[12px] text-fg-3">{meta}</span>}
      </header>
      <div className="grid gap-3 px-4 py-3">{children}</div>
    </section>
  );
}

export function KeyValue({ k, v }: { k: ReactNode; v: ReactNode }) {
  return (
    <div className="flex justify-between gap-3 border-b border-line py-2 text-[12.5px] last:border-b-0">
      <span className="text-fg-2">{k}</span>
      <span className="text-right text-fg">{v}</span>
    </div>
  );
}
