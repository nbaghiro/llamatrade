// Block kinds as token classes. Kinds differ by rail weight and keyword, never by gain or loss colours;
// the accent marks selection only.

export type BlockKindKey =
  | 'strategy'
  | 'root'
  | 'if'
  | 'filter'
  | 'weight'
  | 'else'
  | 'group'
  | 'asset';

export interface BlockKindStyle {
  /** Left rail and fill. */
  box: string;
  /** Keyword colour. */
  kw: string;
}

const STYLES: Record<BlockKindKey, BlockKindStyle> = {
  strategy: { box: 'bg-panel border-l-[3px] border-l-fg', kw: 'text-fg' },
  root: { box: 'bg-panel border-l-[3px] border-l-fg', kw: 'text-fg' },
  if: { box: 'bg-sunk border-l-[3px] border-l-fg-2', kw: 'text-fg' },
  filter: { box: 'bg-sunk border-l-[3px] border-l-fg-2', kw: 'text-fg' },
  else: { box: 'bg-sunk border-l-[3px] border-l-fg-3', kw: 'text-fg-2' },
  weight: { box: 'bg-panel border-l-[3px] border-l-chart-3', kw: 'text-fg-2' },
  group: { box: 'bg-panel border-l-[3px] border-l-line-strong', kw: 'text-fg-2' },
  asset: { box: 'bg-panel border-l-[3px] border-l-chart-4', kw: 'text-fg-3' },
};

export const SELECTED_BLOCK = 'ring-2 ring-accent ring-offset-2 ring-offset-canvas';

export function blockStyle(kind: BlockKindKey): BlockKindStyle {
  return STYLES[kind];
}
