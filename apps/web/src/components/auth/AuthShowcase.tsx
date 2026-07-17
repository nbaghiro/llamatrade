import { useEffect, useState } from 'react';

import { MARKETING_URL } from '../../config/marketing';
import { Logo } from '../common/Logo';
import { Marquee } from '../common/Marquee';
import { StrategyTree, type RawNode } from '../common/StrategyTree';
import { prepareTree } from '../common/strategyTreeModel';


/**
 * AuthShowcase — the animated left panel of the split-screen auth experience.
 *
 * Concept: "the strategy builds itself." A mini node/tree editor (mirroring the
 * app's real visual builder, in the brutalist "Monolith" theme) assembles a real
 * strategy block-by-block, holds, then wipes and builds the NEXT one — rotating
 * through several genuinely different strategies so it never feels repetitive.
 * Every block/DSL token shown is valid grammar (see `libs/dsl/llamatrade_dsl`:
 * INDICATORS, METRICS, weight :method values, rebalance frequencies).
 *
 * The block-tree renderer + ticker are the shared Monolith design-system pieces
 * (`StrategyTree`, `Marquee`) from `../common`; this file keeps only the
 * auth-specific strategy data, cycling logic, and split-panel chrome.
 *
 * Reduced-motion aware: renders the first strategy fully composed and never loops.
 */

/**
 * Four real, grammar-valid strategies (equivalent DSL in each comment).
 * They vary in shape — trend gate, flat risk-parity, momentum rotation,
 * RSI mean-reversion — so the loop stays interesting.
 */
const RAW_STRATEGIES: RawNode[] = [
  // (strategy "Momentum + Trend Guard" :rebalance monthly :benchmark SPY
  //   (if (> (price SPY) (sma SPY 200))
  //     (filter :by momentum :select (top 3) :lookback 90
  //       (weight :method equal (asset XLK) (asset XLF) (asset XLV)))
  //     (else (weight :method equal (asset BIL)))))
  {
    kind: 'strategy',
    kw: 'STRATEGY',
    label: '"Momentum + Trend Guard" · monthly · SPY',
    children: [
      {
        kind: 'if',
        kw: 'IF',
        label: '(> (price SPY) (sma SPY 200))',
        children: [
          {
            kind: 'filter',
            kw: 'FILTER',
            label: ':by momentum · (top 3) · 90d',
            children: [
              {
                kind: 'weight',
                kw: 'WEIGHT',
                label: ':method equal',
                children: [
                  { kind: 'asset', kw: '', label: 'XLK · Technology', weight: '33%' },
                  { kind: 'asset', kw: '', label: 'XLF · Financials', weight: '33%' },
                  { kind: 'asset', kw: '', label: 'XLV · Health Care', weight: '34%' },
                ],
              },
            ],
          },
          {
            kind: 'else',
            kw: 'ELSE',
            label: '· risk-off',
            children: [
              {
                kind: 'weight',
                kw: 'WEIGHT',
                label: ':method equal',
                children: [{ kind: 'asset', kw: '', label: 'BIL · 1–3M T-Bills', weight: '100%' }],
              },
            ],
          },
        ],
      },
    ],
  },

  // (strategy "All-Weather Parity" :rebalance quarterly :benchmark SPY
  //   (weight :method risk-parity
  //     (asset VTI) (asset TLT) (asset IEF) (asset GLD) (asset DBC)))
  {
    kind: 'strategy',
    kw: 'STRATEGY',
    label: '"All-Weather Parity" · quarterly · SPY',
    children: [
      {
        kind: 'weight',
        kw: 'WEIGHT',
        label: ':method risk-parity',
        children: [
          { kind: 'asset', kw: '', label: 'VTI · US Equity' },
          { kind: 'asset', kw: '', label: 'TLT · Long Treasury' },
          { kind: 'asset', kw: '', label: 'IEF · 7–10Y Treasury' },
          { kind: 'asset', kw: '', label: 'GLD · Gold' },
          { kind: 'asset', kw: '', label: 'DBC · Commodities' },
        ],
      },
    ],
  },

  // (strategy "Sector Rotation" :rebalance monthly :benchmark SPY
  //   (filter :by momentum :select (top 4) :lookback 120
  //     (weight :method inverse-volatility
  //       (asset XLK) (asset XLV) (asset XLE) (asset XLF) (asset XLI) (asset XLY))))
  {
    kind: 'strategy',
    kw: 'STRATEGY',
    label: '"Sector Rotation" · monthly · SPY',
    children: [
      {
        kind: 'filter',
        kw: 'FILTER',
        label: ':by momentum · (top 4) · 120d',
        children: [
          {
            kind: 'weight',
            kw: 'WEIGHT',
            label: ':method inverse-volatility',
            children: [
              { kind: 'asset', kw: '', label: 'XLK · Technology' },
              { kind: 'asset', kw: '', label: 'XLV · Health Care' },
              { kind: 'asset', kw: '', label: 'XLE · Energy' },
              { kind: 'asset', kw: '', label: 'XLF · Financials' },
              { kind: 'asset', kw: '', label: 'XLI · Industrials' },
              { kind: 'asset', kw: '', label: 'XLY · Consumer Disc.' },
            ],
          },
        ],
      },
    ],
  },

  // (strategy "Mean Reversion" :rebalance weekly :benchmark QQQ
  //   (if (< (rsi QQQ 14) 30)
  //     (weight :method specified (asset TQQQ 0.5) (asset QQQ 0.5))
  //     (else (weight :method equal (asset SHY)))))
  {
    kind: 'strategy',
    kw: 'STRATEGY',
    label: '"Mean Reversion" · weekly · QQQ',
    children: [
      {
        kind: 'if',
        kw: 'IF',
        label: '(< (rsi QQQ 14) 30)',
        children: [
          {
            kind: 'weight',
            kw: 'WEIGHT',
            label: ':method specified',
            children: [
              { kind: 'asset', kw: '', label: 'TQQQ · 3× Nasdaq 100', weight: '50%' },
              { kind: 'asset', kw: '', label: 'QQQ · Nasdaq 100', weight: '50%' },
            ],
          },
          {
            kind: 'else',
            kw: 'ELSE',
            label: '· cash',
            children: [
              {
                kind: 'weight',
                kw: 'WEIGHT',
                label: ':method equal',
                children: [{ kind: 'asset', kw: '', label: 'SHY · 1–3Y Treasury', weight: '100%' }],
              },
            ],
          },
        ],
      },
    ],
  },
];

const STRATEGIES = RAW_STRATEGIES.map(prepareTree);

const REVEAL_MS = 360; // per-block build cadence
const HOLD_MS = 2800; // pause on the completed strategy
const CLEAR_MS = 480; // wipe before the next strategy
const START_DELAY_MS = 450;

const MARQUEE_ITEMS = [
  'VISUAL BLOCK BUILDER',
  'S-EXPRESSION DSL',
  'AI COPILOT',
  'SHARPE / SORTINO',
  'MAX DRAWDOWN',
  'EQUITY CURVE',
  'LIVE = BACKTEST',
  'DOUBLE-ENTRY LEDGER',
  'PAPER → LIVE',
  'OPEN SOURCE',
];

function usePrefersReducedMotion(): boolean {
  const [reduce] = useState<boolean>(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });
  return reduce;
}

export function AuthShowcase() {
  const reduce = usePrefersReducedMotion();
  const [index, setIndex] = useState<number>(0);
  const [visibleCount, setVisibleCount] = useState<number>(reduce ? STRATEGIES[0].count : 0);

  useEffect(() => {
    if (reduce) return;
    let si = 0;
    let vc = 0;
    let phase: 'build' | 'hold' | 'clear' = 'build';
    let timer: ReturnType<typeof setTimeout>;

    const step = () => {
      const total = STRATEGIES[si].count;
      if (phase === 'build') {
        if (vc < total) {
          vc += 1;
          setVisibleCount(vc);
          timer = setTimeout(step, REVEAL_MS);
        } else {
          phase = 'hold';
          timer = setTimeout(step, HOLD_MS);
        }
      } else if (phase === 'hold') {
        phase = 'clear';
        vc = 0;
        setVisibleCount(0);
        timer = setTimeout(step, CLEAR_MS);
      } else {
        si = (si + 1) % STRATEGIES.length;
        setIndex(si);
        phase = 'build';
        timer = setTimeout(step, REVEAL_MS);
      }
    };

    timer = setTimeout(step, START_DELAY_MS);
    return () => clearTimeout(timer);
  }, [reduce]);

  const current = STRATEGIES[index];
  const compiled = visibleCount >= current.count;

  return (
    <aside
      className="relative hidden overflow-hidden bg-ink lg:flex lg:w-[56%] lg:flex-col"
      aria-label="LlamaTrade strategy builder preview"
    >
      <style>{`
        @keyframes lt-blink { 0%, 49% { opacity: 1; } 50%, 100% { opacity: 0; } }
        .lt-cursor { animation: lt-blink 1s steps(1) infinite; }
        @media (prefers-reduced-motion: reduce) {
          .lt-cursor { animation: none; }
        }
      `}</style>

      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage: 'radial-gradient(rgb(var(--lt-bone) / 0.1) 1.1px, transparent 1.1px)',
          backgroundSize: '22px 22px',
        }}
      />

      <div className="relative flex flex-1 flex-col justify-between gap-10 p-10 xl:p-12">
        <div className="flex items-center justify-between">
          <a
            href={MARKETING_URL}
            aria-label="LlamaTrade — back to home"
            className="flex items-center gap-3 transition-opacity hover:opacity-80"
          >
            <Logo size={38} />
            <div className="leading-none">
              <div className="font-display text-xl uppercase tracking-tight text-bone">LlamaTrade</div>
              <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.2em] text-bone/50">
                Algorithmic Trading
              </div>
            </div>
          </a>
          <span className="border-2 border-orange-500 px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-wider text-orange-500">
            Paper-First Beta
          </span>
        </div>

        <div className="flex min-h-0 flex-col gap-6">
          <div>
            <h2 className="font-display text-5xl uppercase leading-[0.92] tracking-tight text-bone xl:text-6xl">
              Build the machine.
              <br />
              <span className="text-orange-500">Trade your own account.</span>
            </h2>
            <p className="mt-4 max-w-md font-sans text-sm text-bone/60">
              The exact strategy you backtest is the code that trades live. No translation, no drift.
            </p>
          </div>

          {/* Mini node/tree editor — cycles through strategies */}
          <div className="border-2 border-bone/15">
            <div className="flex items-center justify-between border-b-2 border-bone/15 bg-bone/[0.04] px-3 py-2 font-mono text-[10px] font-bold uppercase tracking-wider text-bone/55">
              <span className="flex items-center gap-2">
                <span className="h-2 w-2 bg-orange-500" aria-hidden="true" />
                strategy.lt
              </span>
              <span>Tree View</span>
            </div>

            {/* All strategies share one grid cell so the panel height stays fixed to the
                tallest DSL; only the active one is visible, the rest reserve layout. */}
            <div className="grid overflow-hidden px-4 py-4 text-bone" style={{ minHeight: 434 }}>
              {STRATEGIES.map((strategy, i) => (
                <div
                  key={i}
                  aria-hidden={i !== index}
                  className="col-start-1 row-start-1"
                  style={{ visibility: i === index ? 'visible' : 'hidden' }}
                >
                  <StrategyTree
                    node={strategy.tree}
                    visibleCount={i === index ? visibleCount : 0}
                  />
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between border-t-2 border-bone/15 px-3 py-2 font-mono text-[10px] font-bold uppercase tracking-wider">
              <span className={compiled ? 'text-green-400' : 'text-bone/55'}>
                {compiled
                  ? '> compiled OK · 0 errors'
                  : `> building · ${visibleCount}/${current.count} blocks`}
                <span className="lt-cursor ml-1 inline-block h-[11px] w-[7px] translate-y-[1px] bg-orange-500 align-middle" />
              </span>
              <span className="text-bone/40">DSL · v1</span>
            </div>
          </div>
        </div>

        <Marquee
          items={MARQUEE_ITEMS}
          speed={28}
          className="-mx-10 border-y-2 border-bone/15 py-3 xl:-mx-12"
          trackClassName="text-bone/45"
        />
      </div>
    </aside>
  );
}
