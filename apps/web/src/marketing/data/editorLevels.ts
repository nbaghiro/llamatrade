/** The three strategies behind the Build tabs: Starter, Tactical and Advanced. */

/** Bar shades from the chart ramp; hacc is the accent and hfree the hatched unallocated share. */
export type Shade = 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'hacc' | 'hfree';

export interface TreeAsset {
  kind: 'asset';
  sym: string;
  name: string;
  shade: Shade;
  weight: number;
  /** Not held: ranked out, or under a branch that doesn't apply today. */
  muted?: boolean;
}

export interface TreeBlock {
  kind: 'block';
  keyword: string;
  label: string;
  note: string;
  noteStyle: 'text' | 'chip' | 'chip-ok';
  /** on: applies today; off: a branch that doesn't. */
  state?: 'on' | 'off';
  children?: { on: boolean; items: TreeItem[] };
}

export type TreeItem = TreeAsset | TreeBlock;

export interface EditorLevel {
  id: 'starter' | 'tactical' | 'advanced';
  tab: string;
  name: string;
  meta: string;
  tree: TreeItem[];
  code: string[];
  hold: { shade: Shade; weight: number; sym: string }[];
  needs: [string, string][];
}

const asset = (
  sym: string,
  name: string,
  shade: Shade,
  weight: number,
  muted = false
): TreeAsset => ({
  kind: 'asset',
  sym,
  name,
  shade,
  weight,
  muted,
});

const starter: EditorLevel = {
  id: 'starter',
  tab: 'Starter',
  name: 'Core Four',
  meta: 'Version 1 · quarterly · benchmark SPY',
  tree: [
    {
      kind: 'block',
      keyword: 'Weight',
      label: 'Equal',
      note: '4 assets',
      noteStyle: 'text',
      state: 'on',
      children: {
        on: true,
        items: [
          asset('VTI', 'Vanguard Total Stock Market', 'h1', 25),
          asset('VXUS', 'Vanguard Total International', 'h2', 25),
          asset('BND', 'Vanguard Total Bond Market', 'h3', 25),
          asset('GLD', 'SPDR Gold Shares', 'h4', 25),
        ],
      },
    },
  ],
  code: [
    '(strategy "Core Four"',
    '  :rebalance quarterly :benchmark SPY',
    '  (weight :method equal',
    '    (asset VTI) (asset VXUS)',
    '    (asset BND) (asset GLD)))',
  ],
  hold: [
    { shade: 'h1', weight: 25, sym: 'VTI' },
    { shade: 'h2', weight: 25, sym: 'VXUS' },
    { shade: 'h3', weight: 25, sym: 'BND' },
    { shade: 'h4', weight: 25, sym: 'GLD' },
  ],
  needs: [
    ['Symbols', '4'],
    ['History', '1 bar'],
    ['Rebalance', 'Quarterly'],
  ],
};

const tactical: EditorLevel = {
  id: 'tactical',
  tab: 'Tactical',
  name: 'Tech Momentum Rotation',
  meta: 'Version 2 · monthly · benchmark QQQ',
  tree: [
    {
      kind: 'block',
      keyword: 'Filter',
      label: 'Momentum · top 2 of 3 · 90 days',
      note: 'ranks by return',
      noteStyle: 'text',
      children: {
        on: true,
        items: [
          {
            kind: 'block',
            keyword: 'Weight',
            label: 'Equal',
            note: '2 held',
            noteStyle: 'text',
            state: 'on',
            children: {
              on: true,
              items: [
                asset('SMH', 'VanEck Semiconductor', 'h1', 50),
                asset('QQQ', 'Invesco QQQ Trust', 'h3', 50),
                asset('XLK', 'Technology Select · third', 'h5', 0, true),
              ],
            },
          },
        ],
      },
    },
  ],
  code: [
    '(strategy "Tech Momentum Rotation"',
    '  :rebalance monthly :benchmark QQQ',
    '  (filter :by momentum :select (top 2)',
    '          :lookback 90',
    '    (weight :method equal',
    '      (asset QQQ) (asset XLK)',
    '      (asset SMH))))',
  ],
  hold: [
    { shade: 'h1', weight: 50, sym: 'SMH' },
    { shade: 'h3', weight: 50, sym: 'QQQ' },
  ],
  needs: [
    ['Symbols', '3'],
    ['History', '90 bars'],
    ['Rebalance', 'Monthly'],
  ],
};

const advanced: EditorLevel = {
  id: 'advanced',
  tab: 'Advanced',
  name: 'Recession Radar',
  meta: 'Version 3 · monthly · benchmark SPY',
  tree: [
    {
      kind: 'block',
      keyword: 'If',
      label: 'RSI(SPY, 14) above 70',
      note: '58.4 today · false',
      noteStyle: 'chip',
      children: {
        on: false,
        items: [
          {
            kind: 'block',
            keyword: 'Weight',
            label: 'Specified',
            note: 'not applied',
            noteStyle: 'text',
            state: 'off',
            children: {
              on: false,
              items: [
                asset('TLT', 'iShares 20+ Year Treasury', 'h1', 60, true),
                asset('GLD', 'SPDR Gold Shares', 'h3', 40, true),
              ],
            },
          },
        ],
      },
    },
    {
      kind: 'block',
      keyword: 'Else',
      label: 'Momentum · top 2 of 3 · 90 days',
      note: 'Applies today',
      noteStyle: 'chip-ok',
      state: 'on',
      children: {
        on: true,
        items: [
          asset('QQQ', 'Invesco QQQ Trust', 'hacc', 54.3),
          asset('VTI', 'Vanguard Total Stock Market', 'h2', 45.7),
          asset('IWM', 'iShares Russell 2000 · third', 'h5', 0, true),
        ],
      },
    },
  ],
  code: [
    '(strategy "Recession Radar"',
    '  :rebalance monthly :benchmark SPY',
    '  (if (> (rsi SPY 14) 70)',
    '      (weight :method specified',
    '        (asset TLT :weight 60)',
    '        (asset GLD :weight 40))',
    '      (else',
    '        (weight :method momentum',
    '          :lookback 90 :top 2',
    '          (asset VTI) (asset QQQ)',
    '          (asset IWM)))))',
  ],
  hold: [
    { shade: 'hacc', weight: 54.3, sym: 'QQQ' },
    { shade: 'h2', weight: 45.7, sym: 'VTI' },
  ],
  needs: [
    ['Symbols', '6 · SPY as signal'],
    ['History', '90 bars'],
    ['Rebalance', 'Monthly'],
  ],
};

export const EDITOR_LEVELS: readonly EditorLevel[] = [starter, tactical, advanced];

/** The level the Build tabs and the screen art open on. */
export const DEFAULT_LEVEL = 2;
