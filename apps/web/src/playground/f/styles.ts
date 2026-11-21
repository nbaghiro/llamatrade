/** A 32px ledger row; the selected one carries an ink bar on its left edge. */
export const rowClass = (selected: boolean) =>
  `relative grid h-8 cursor-pointer items-center gap-3 border-b border-line px-3 text-[13px] last:border-b-0 ${
    selected
      ? 'bg-sunk before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-fg'
      : 'hover:bg-panel'
  }`;
