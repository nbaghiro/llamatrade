import type { RawNode } from '../../components/common/StrategyTree';

import { k, p, s, type CodeLine } from '../components/codeTokens';

/**
 * The three strategy-complexity levels shown in the "01 BUILD" block editor.
 * Each level carries a `tree` (rendered by the shared <StrategyTree>) and the
 * equivalent `code` view (the same strategy as valid libs/dsl S-expressions,
 * copied verbatim from the original static page).
 *
 * Group/wgroup nodes from the original tree mockup have no equivalent in the
 * shared StrategyTree kinds, so the Advanced tree folds the group label into its
 * WEIGHT block and renders the weighted sub-sleeves as badged weight blocks —
 * the code view keeps the exact `(group …)` DSL.
 */
export interface EditorLevelTab {
  lv: string;
  dots: [boolean, boolean, boolean];
  sub: string;
}

export interface EditorLevelFoot {
  pre: string;
  bold: string;
  post: string;
}

export interface EditorLevel {
  id: 'starter' | 'tactical' | 'advanced';
  tab: EditorLevelTab;
  name: string;
  tree: RawNode;
  code: CodeLine[];
  addLabel: string;
  foot: EditorLevelFoot;
}

const asset = (label: string): RawNode => ({ kind: 'asset', kw: '', label });

const ADD_FULL = '＋ Add a Block  ·  Stocks or Securities, Weights, Conditions…';
const ADD_SHORT = '＋ Add a Block …';

// ── 01 · Starter · Core Four ────────────────────────────────────────────────
const starter: EditorLevel = {
  id: 'starter',
  tab: { lv: '01 · Starter', dots: [true, false, false], sub: 'Buy & hold' },
  name: 'Core Four',
  tree: {
    kind: 'weight',
    kw: 'WEIGHT',
    label: '· Equal',
    children: [
      asset('VTI · Total US Market'),
      asset('VXUS · Total International'),
      asset('BND · Total Bond Market'),
      asset('GLD · Gold'),
    ],
  },
  code: [
    [k('(strategy'), p(' '), s('"Core Four"')],
    [p('  '), k(':rebalance'), p(' quarterly')],
    [p('  '), k(':benchmark'), p(' '), s('SPY')],
    [p('  '), k('(weight'), p(' '), k(':method'), p(' equal')],
    [p('    ('), k('asset'), p(' '), s('VTI'), p(')')],
    [p('    ('), k('asset'), p(' '), s('VXUS'), p(')')],
    [p('    ('), k('asset'), p(' '), s('BND'), p(')')],
    [p('    ('), k('asset'), p(' '), s('GLD'), p(')))')],
  ],
  addLabel: ADD_FULL,
  foot: { pre: '1 sleeve · ', bold: '4 tickers', post: ' · equal-weight · compiled ✓' },
};

// ── 02 · Tactical · Tech Momentum Rotation ──────────────────────────────────
const tactical: EditorLevel = {
  id: 'tactical',
  tab: { lv: '02 · Tactical', dots: [true, true, false], sub: 'Rank & rotate' },
  name: 'Tech Momentum Rotation',
  tree: {
    kind: 'filter',
    kw: 'FILTER',
    label: '· by momentum · select top 2 · lookback 90',
    children: [
      {
        kind: 'weight',
        kw: 'WEIGHT',
        label: '· Equal',
        children: [
          asset('QQQ · Nasdaq 100'),
          asset('XLK · Tech Sector'),
          asset('SMH · Semiconductors'),
          asset('SOXX · Chip Makers'),
          asset('VGT · Info Tech'),
        ],
      },
    ],
  },
  code: [
    [k('(strategy'), p(' '), s('"Tech Momentum Rotation"')],
    [p('  '), k(':rebalance'), p(' monthly')],
    [p('  '), k(':benchmark'), p(' '), s('QQQ')],
    [
      p('  '),
      k('(filter'),
      p(' '),
      k(':by'),
      p(' momentum '),
      k(':select'),
      p(' (top 2) '),
      k(':lookback'),
      p(' 90'),
    ],
    [p('    '), k('(weight'), p(' '), k(':method'), p(' equal')],
    [p('      ('), k('asset'), p(' '), s('QQQ'), p(')')],
    [p('      ('), k('asset'), p(' '), s('XLK'), p(')')],
    [p('      ('), k('asset'), p(' '), s('SMH'), p(')')],
    [p('      ('), k('asset'), p(' '), s('SOXX'), p(')')],
    [p('      ('), k('asset'), p(' '), s('VGT'), p('))))')],
  ],
  addLabel: ADD_SHORT,
  foot: { pre: '1 filter · ', bold: 'select top 2 of 5', post: ' · 1 sleeve · compiled ✓' },
};

// ── 03 · Advanced · Income Regime Switch ────────────────────────────────────
const advanced: EditorLevel = {
  id: 'advanced',
  tab: { lv: '03 · Advanced', dots: [true, true, true], sub: 'Regime switch' },
  name: 'Income Regime Switch',
  tree: {
    kind: 'if',
    kw: 'IF',
    label: 'close of TLT is greater than the 50-day moving average of close of TLT',
    children: [
      {
        kind: 'if',
        kw: 'IF',
        label: 'the 60-day moving average of close of SCHD is greater than 0',
        children: [
          {
            kind: 'weight',
            kw: 'WEIGHT',
            label: '· Specified · Falling Rates + Strong Dividends',
            children: [
              { kind: 'weight', kw: '', label: 'Duration', weight: '35%' },
              { kind: 'weight', kw: '', label: 'Corporate Bonds', weight: '25%' },
              { kind: 'weight', kw: '', label: 'Dividend Equity', weight: '40%' },
            ],
          },
        ],
      },
      {
        kind: 'else',
        kw: 'ELSE',
        label: '',
        children: [
          { kind: 'weight', kw: 'WEIGHT', label: '· Equal', children: [asset('BIL · US T-Bills')] },
        ],
      },
    ],
  },
  code: [
    [k('(strategy'), p(' '), s('"Income Regime Switch"')],
    [p('  '), k(':rebalance'), p(' monthly')],
    [p('  '), k(':benchmark'), p(' '), s('AGG')],
    [
      p('  '),
      k('(if'),
      p(' (> ('),
      k('price'),
      p(' '),
      s('TLT'),
      p(') ('),
      k('sma'),
      p(' '),
      s('TLT'),
      p(' 50))'),
    ],
    [p('    '), k('(if'), p(' (> ('), k('sma'), p(' '), s('SCHD'), p(' 60) 0)')],
    [p('      '), k('(group'), p(' '), s('"Falling Rates + Strong Dividends"')],
    [p('        '), k('(weight'), p(' '), k(':method'), p(' specified')],
    [p('          '), k('(group'), p(' '), s('"Duration"'), p(' '), k(':weight'), p(' 35')],
    [
      p('            '),
      k('(weight'),
      p(' '),
      k(':method'),
      p(' equal ('),
      k('asset'),
      p(' '),
      s('TLT'),
      p(') ('),
      k('asset'),
      p(' '),
      s('EDV'),
      p(')))'),
    ],
    [p('          '), k('(group'), p(' '), s('"Corporate Bonds"'), p(' '), k(':weight'), p(' 25')],
    [
      p('            '),
      k('(weight'),
      p(' '),
      k(':method'),
      p(' equal ('),
      k('asset'),
      p(' '),
      s('LQD'),
      p(') ('),
      k('asset'),
      p(' '),
      s('VCIT'),
      p(')))'),
    ],
    [p('          '), k('(group'), p(' '), s('"Dividend Equity"'), p(' '), k(':weight'), p(' 40')],
    [
      p('            '),
      k('(weight'),
      p(' '),
      k(':method'),
      p(' equal ('),
      k('asset'),
      p(' '),
      s('SCHD'),
      p(') ('),
      k('asset'),
      p(' '),
      s('VYM'),
      p('))))))'),
    ],
    [p('    '), k('(else')],
    [
      p('      '),
      k('(weight'),
      p(' '),
      k(':method'),
      p(' equal ('),
      k('asset'),
      p(' '),
      s('BIL'),
      p(')))))'),
    ],
  ],
  addLabel: ADD_SHORT,
  foot: { pre: '2 branches · 3 sleeves · ', bold: '7 tickers', post: ' · compiled ✓' },
};

export const EDITOR_LEVELS: EditorLevel[] = [starter, tactical, advanced];

// ── Extra DSL example · Dual Momentum + Crash Guard ─────────────────────────
export const DSL_EXAMPLE: CodeLine[] = [
  [k('(strategy'), p(' '), s('"Dual Momentum + Crash Guard"')],
  [p('  '), k(':rebalance'), p(' monthly')],
  [p('  '), k(':benchmark'), p(' '), s('SPY')],
  [
    p('  '),
    k('(if'),
    p(' (> ('),
    k('price'),
    p(' '),
    s('SPY'),
    p(') ('),
    k('sma'),
    p(' '),
    s('SPY'),
    p(' 200))'),
  ],
  [p('    '), k('(group'), p(' '), s('"Risk-On"')],
  [
    p('      '),
    k('(filter'),
    p(' '),
    k(':by'),
    p(' momentum '),
    k(':select'),
    p(' (top 3) '),
    k(':lookback'),
    p(' 120'),
  ],
  [
    p('        '),
    k('(weight'),
    p(' '),
    k(':method'),
    p(' inverse-volatility '),
    k(':lookback'),
    p(' 60'),
  ],
  [
    p('          ('),
    k('asset'),
    p(' '),
    s('QQQ'),
    p(') ('),
    k('asset'),
    p(' '),
    s('XLK'),
    p(') ('),
    k('asset'),
    p(' '),
    s('SMH'),
    p(')'),
  ],
  [
    p('          ('),
    k('asset'),
    p(' '),
    s('XLF'),
    p(') ('),
    k('asset'),
    p(' '),
    s('XLE'),
    p(') ('),
    k('asset'),
    p(' '),
    s('XLV'),
    p(')))'),
  ],
  [p('    '), k('(else')],
  [p('      '), k('(group'), p(' '), s('"Risk-Off"')],
  [p('        '), k('(weight'), p(' '), k(':method'), p(' specified')],
  [p('          ('), k('asset'), p(' '), s('IEF'), p(' '), k(':weight'), p(' 60)')],
  [p('          ('), k('asset'), p(' '), s('GLD'), p(' '), k(':weight'), p(' 40))))))')],
];
