import type { ReactNode } from 'react';

import { PaperPill } from '../shell/PaperPill';

export interface RailItem {
  label: string;
  value: ReactNode;
  /** Amber, for something that needs the person. */
  attention?: boolean;
}

/** A thin rail of live facts under the top bar: market, data, rebalance and reconciliation. */
export function StatusRail({ items }: { items: readonly RailItem[] }) {
  return (
    <div
      role="region"
      aria-label="Trading status"
      className="no-scrollbar flex overflow-x-auto border-b border-line bg-sunk text-[11px]"
    >
      {items.map((it) => (
        <div
          key={it.label}
          className="flex flex-none flex-col gap-0.5 whitespace-nowrap border-r border-line px-3.5 py-1.5"
        >
          <span className="text-[10px] text-fg-3">{it.label}</span>
          <span
            className={`num text-[11.5px] font-medium ${it.attention ? 'text-risk' : 'text-fg'}`}
          >
            {it.value}
          </span>
        </div>
      ))}
      <div className="ml-auto flex flex-none items-center px-3.5">
        <PaperPill />
      </div>
    </div>
  );
}
