import { useCallback, useEffect, useMemo, useState } from 'react';

import { StrategyTree } from '../../components/common/StrategyTree';
import { prepareTree } from '../../components/common/strategyTreeModel';
import { CodeBlock, MiniCode } from '../components/CodeBlock';
import { k, nb, p, s, type CodeLine } from '../components/codeTokens';
import { DSL_EXAMPLE, EDITOR_LEVELS } from '../data/editorLevels';

// ── Card B / Card C compact DSL snippets (`.code-mini`, no white-space:pre) ──
const CARD_B_CODE: CodeLine[] = [
  [k('(strategy'), p(' '), s('"Momentum + Trend Guard"')],
  [nb(2), k(':rebalance'), p(' monthly '), k(':benchmark'), p(' '), s('SPY')],
  [nb(2), k('(if'), p(' (> ('), s('price'), p(' SPY) ('), s('sma'), p(' SPY 200))')],
  [
    nb(4),
    k('(filter'),
    p(' '),
    k(':by'),
    p(' momentum '),
    k(':select'),
    p(' (top 3) '),
    k(':lookback'),
    p(' 90'),
  ],
  [nb(6), k('(weight'), p(' '), k(':method'), p(' equal')],
  [nb(8), k('(asset'), p(' '), s('XLK)')],
  [nb(8), k('(asset'), p(' '), s('XLF)')],
  [nb(8), k('(asset'), p(' '), s('XLV)'), p(' '), k('(asset'), p(' '), s('XLP)'), p('))')],
  [nb(4), k('(else'), p(' '), k('(if'), p(' (< ('), s('rsi'), p(' SPY 14) 30)')],
  [nb(6), k('(weight'), p(' '), k(':method'), p(' equal '), k('(asset'), p(' '), s('SPY'), p('))')],
  [
    nb(6),
    k('(else'),
    p(' '),
    k('(weight'),
    p(' '),
    k(':method'),
    p(' equal '),
    k('(asset'),
    p(' '),
    s('BIL'),
    p(')))))))'),
  ],
];

const CARD_C_CODE: CodeLine[] = [
  [
    k('(strategy'),
    p(' '),
    s('"Tech Momentum Rotation"'),
    p(' '),
    k(':rebalance'),
    p(' monthly'),
  ],
  [
    nb(2),
    k('(filter'),
    p(' '),
    k(':by'),
    p(' momentum '),
    k(':select'),
    p(' (top 2) '),
    k(':lookback'),
    p(' 90'),
  ],
  [nb(4), k('(weight'), p(' '), k(':method'), p(' equal')],
  [
    nb(6),
    k('(asset'),
    p(' '),
    s('QQQ)'),
    p(' '),
    k('(asset'),
    p(' '),
    s('XLK)'),
    p(' '),
    k('(asset'),
    p(' '),
    s('SMH)'),
    p(' …)))'),
  ],
];

// Shared header-bar glyphs (identical across the three complexity levels).
function EdBarIcons() {
  return (
    <>
      <span className="ico" aria-hidden="true">
        <svg viewBox="0 0 20 20">
          <path d="M4 7 L10 13 L16 7" />
        </svg>
      </span>
      <span className="ico" aria-hidden="true">
        <svg viewBox="0 0 20 20">
          <path d="M10 2 L18 6 L10 10 L2 6 Z" />
          <path d="M3 10 L10 13.5 L17 10" />
          <path d="M3 13.5 L10 17 L17 13.5" />
        </svg>
      </span>
    </>
  );
}

function Editor() {
  const [active, setActive] = useState(0);
  const [codeById, setCodeById] = useState<Record<string, boolean>>({});

  const level = EDITOR_LEVELS[active];
  const showCode = codeById[level.id] ?? false;

  const toggleActive = useCallback(() => {
    const id = EDITOR_LEVELS[active].id;
    setCodeById((prev) => ({ ...prev, [id]: !(prev[id] ?? false) }));
  }, [active]);

  // ⌘K / Ctrl-K: toggle code ⇄ tree on the currently visible level.
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        toggleActive();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [toggleActive]);

  const tree = useMemo(() => prepareTree(level.tree).tree, [level.tree]);

  return (
    <div className="editor reveal" aria-label="LlamaTrade block editor">
      {/* strategy-complexity switcher */}
      <div className="ed-levels" role="tablist" aria-label="Strategy complexity">
        {EDITOR_LEVELS.map((lvl, i) => (
          <button
            key={lvl.id}
            className={`ed-lvl${i === active ? ' is-active' : ''}`}
            role="tab"
            aria-selected={i === active}
            type="button"
            onClick={() => setActive(i)}
          >
            <span className="lv">{lvl.tab.lv}</span>{' '}
            <span className="dots" aria-hidden="true">
              {lvl.tab.dots.map((on, di) => (
                <span key={di} className={on ? 'on' : undefined}>
                  {on ? '●' : '○'}
                </span>
              ))}
            </span>{' '}
            <span className="lvsub">{lvl.tab.sub}</span>
          </button>
        ))}
      </div>

      {/* header bar */}
      <div className="ed-bar">
        <div className="grp">
          <EdBarIcons />
          <span className="ed-name">{level.name}</span>
          <span className="ico" aria-hidden="true">
            <svg viewBox="0 0 20 20">
              <path d="M1.5 10 C4.5 4.5 15.5 4.5 18.5 10 C15.5 15.5 4.5 15.5 1.5 10 Z" />
              <circle cx="10" cy="10" r="2.6" />
            </svg>
          </span>
        </div>
        <div className="grp">
          <span className="ico" aria-hidden="true">
            <svg viewBox="0 0 20 20">
              <circle cx="6" cy="4" r="2.1" />
              <circle cx="6" cy="16" r="2.1" />
              <circle cx="14" cy="6.5" r="2.1" />
              <path d="M6 6.1 L6 13.9" />
              <path d="M13.9 8 C12.5 11 8 9.6 6 11.4" />
            </svg>
          </span>
          <button
            className="ed-toggle"
            type="button"
            aria-pressed={showCode}
            aria-label="Toggle between tree view and code view"
            onClick={toggleActive}
          >
            <span className="glyph">&lt;/&gt;</span> <span>{showCode ? 'Tree' : 'Code'}</span>
          </button>
        </div>
      </div>

      {/* body: tree (shared StrategyTree, ink ground) OR code view */}
      {showCode ? (
        <div className="ed-code" data-view="code" aria-label="Equivalent DSL, code view">
          <CodeBlock lines={level.code} />
        </div>
      ) : (
        <div className="ed-tree" data-view="tree">
          <div className="min-w-[520px]">
            <StrategyTree node={tree} />
            <div className="ed-tree-add" role="button" tabIndex={0}>
              {level.addLabel}
            </div>
          </div>
        </div>
      )}

      {/* status / footer bar */}
      <div className="ed-foot">
        <span>
          {level.foot.pre}
          <b>{level.foot.bold}</b>
          {level.foot.post}
        </span>
        <span className="ed-hint">⌘K · toggle code ⇄ tree</span>
      </div>
    </div>
  );
}

export function Build() {
  return (
    <section id="build">
      <div className="wrap">
        <div className="sec-head reveal">
          <span className="sec-idx">01 / BUILD</span>
          <h2 className="sec-title">
            Three ways in.
            <br />
            One machine out.
          </h2>
          <span className="sec-lead">No-code · Code · Plain&nbsp;English</span>
        </div>

        <div className="build-grid">
          {/* A · No-code */}
          <article className="bcard reveal" data-d="1">
            <div className="top">
              <span>A · No-code</span>
              <span className="no">01</span>
            </div>
            <div className="body">
              <h3>Visual block builder</h3>
              <p>
                Drag indicators, conditions and orders onto a grid. Wire the logic. Never touch a
                line of code.
              </p>
              <div className="demo blocks" aria-hidden="true">
                <div className="blk hot">
                  <span>IF · SPY &gt; 200-DAY SMA</span>
                  <span className="pin" />
                </div>
                <div className="blk hot ind">
                  <span>FILTER · BY MOMENTUM · TOP 2</span>
                  <span className="pin" />
                </div>
                <div className="blk wt ind">
                  <span>▼ WEIGHT · METHOD EQUAL</span>
                  <span className="pin" />
                </div>
                <div className="blk ind">
                  <span>ASSET · QQQ / XLK / SMH</span>
                  <span className="pin" />
                </div>
                <div className="blk else">
                  <span>ELSE · ASSET · BIL</span>
                  <span className="pin" />
                </div>
              </div>
            </div>
          </article>

          {/* B · Code */}
          <article className="bcard reveal" data-d="2">
            <div className="top">
              <span>B · Code</span>
              <span className="no">02</span>
            </div>
            <div className="body">
              <h3>The DSL</h3>
              <p>
                A concise S-expression language. Version it, diff it, review it. For traders who
                think in code.
              </p>
              <div className="demo" aria-hidden="true">
                <MiniCode className="code-mini" lines={CARD_B_CODE} />
              </div>
            </div>
          </article>

          {/* C · AI Copilot */}
          <article className="bcard reveal" data-d="3">
            <div className="top">
              <span>C · AI Copilot</span>
              <span className="no">03</span>
            </div>
            <div className="body">
              <h3>Plain English</h3>
              <p>
                Describe the strategy. The copilot writes valid, backtestable DSL you can inspect,
                edit and run.
              </p>
              <div className="demo" aria-hidden="true">
                <div className="chatline">
                  <span className="who">YOU</span> &quot;Momentum rotation across tech ETFs,
                  rebalance monthly.&quot;
                </div>
                <div className="chatline ai">
                  <span className="who">COPILOT</span> Reads that as: rank the tech ETFs by 90-day
                  momentum, hold the top 2 equal-weight, rebalanced monthly.
                </div>
                <MiniCode className="code-mini cc-code" lines={CARD_C_CODE} />
                <div className="cop-tags">
                  <span className="ok">✓ Valid</span>
                  <span className="ok">✓ Backtestable</span>
                  <span>Edit before deploy</span>
                </div>
              </div>
            </div>
          </article>
        </div>

        {/* block / tree editor showcase */}
        <div className="editor-sub reveal">
          <span className="kicker">The block editor — start simple, scale up</span>
          <span className="note">Three levels · Tree ⇄ Code</span>
        </div>

        <Editor />

        {/* second complex DSL example */}
        <div
          className="dsl-example reveal"
          aria-label="Another DSL example: Dual Momentum plus Crash Guard"
        >
          <div className="dx-bar">
            <span>Another example · Dual Momentum + Crash Guard</span>
            <span className="dx-tag">momentum filter · inverse-vol · defensive else</span>
          </div>
          <div className="dx-scroll">
            <CodeBlock lines={DSL_EXAMPLE} />
          </div>
        </div>
      </div>
    </section>
  );
}
