import { AlertTriangle, ChevronDown } from 'lucide-react';
import { useState, type ReactNode } from 'react';

export interface AttentionItem {
  id: string;
  /** Names the problem, e.g. "Recession Radar is frozen." */
  title: string;
  /** Says what it means and what happens next. */
  detail?: string;
  action?: ReactNode;
}

interface AttentionLineProps {
  items: readonly AttentionItem[];
  /** Start with the list of several items open. */
  defaultOpen?: boolean;
  className?: string;
}

/** One amber line above a page. Several issues collapse into a count with a list. */
export function AttentionLine({ items, defaultOpen = false, className = '' }: AttentionLineProps) {
  const [open, setOpen] = useState(defaultOpen);
  if (!items.length) return null;
  const shell = `rounded-[8px] border border-risk-line bg-risk-soft text-[12.5px] text-fg ${className}`;

  if (items.length === 1) {
    const [it] = items;
    return (
      <div role="status" className={`flex items-center gap-2.5 px-3 py-2 ${shell}`}>
        <AlertTriangle className="h-4 w-4 flex-none text-risk" />
        <span className="min-w-0 flex-1">
          <b className="font-semibold text-risk">{it.title}</b>
          {it.detail && <span className="text-fg-2"> {it.detail}</span>}
        </span>
        {it.action}
      </div>
    );
  }

  return (
    <div role="status" className={shell}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 px-3 py-2 text-left"
      >
        <AlertTriangle className="h-4 w-4 flex-none text-risk" />
        <span className="flex-1 font-semibold text-risk">{items.length} things need attention</span>
        <ChevronDown
          className={`h-4 w-4 text-fg-2 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <ul className="m-0 list-none border-t border-risk-line p-0">
          {items.map((it) => (
            <li
              key={it.id}
              className="flex items-center gap-2.5 px-3 py-2 [&+&]:border-t [&+&]:border-risk-line"
            >
              <span className="min-w-0 flex-1">
                <b className="font-semibold">{it.title}</b>
                {it.detail && <span className="text-fg-2"> {it.detail}</span>}
              </span>
              {it.action}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
