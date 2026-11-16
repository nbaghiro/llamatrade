/** Table cell classes shared by the dense tables. */
export const T = {
  table: 'w-full border-collapse text-[12.5px]',
  th: 'whitespace-nowrap border-b border-line px-3 py-2 text-left text-[11px] font-medium text-fg-3 first:pl-3.5 last:pr-3.5',
  thN: 'whitespace-nowrap border-b border-line px-3 py-2 text-right text-[11px] font-medium text-fg-3 first:pl-3.5 last:pr-3.5',
  td: 'h-[30px] whitespace-nowrap border-b border-line px-3 first:pl-3.5 last:pr-3.5 [tr:last-child_&]:border-b-0',
  tdN: 'h-[30px] whitespace-nowrap border-b border-line px-3 text-right font-mono tabular-nums tracking-[-0.01em] first:pl-3.5 last:pr-3.5 [tr:last-child_&]:border-b-0',
  sym: 'font-mono text-[12.5px] font-semibold',
  sub: 'mt-px block text-[11px] font-normal text-fg-3',
  rowSel: 'bg-accent-soft [&>td:first-child]:shadow-[inset_2px_0_0_rgb(var(--accent))]',
  rowRisk: 'bg-risk-soft [&>td:first-child]:shadow-[inset_2px_0_0_rgb(var(--risk))]',
} as const;
