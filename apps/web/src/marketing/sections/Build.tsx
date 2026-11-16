import { useState, type KeyboardEvent } from 'react';

import { ScreenFrame } from '../components/ScreenFrame';
import { SectionArt } from '../components/SectionArt';
import { SectionDivider } from '../components/SectionDivider';
import { DEFAULT_LEVEL, EDITOR_LEVELS } from '../data/editorLevels';
import { DIVIDER } from '../data/sections';

const COLUMNS: readonly [string, string][] = [
  ['Blocks', 'Weights, filters and conditions, without code.'],
  ['Code', 'A short S-expression you can diff and review.'],
  ['Plain English', 'Describe it, then read the rules before saving.'],
];

export function Build() {
  const [level, setLevel] = useState(DEFAULT_LEVEL);

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (level + step + EDITOR_LEVELS.length) % EDITOR_LEVELS.length;
    setLevel(next);
    document.getElementById(`lvl-${EDITOR_LEVELS[next].id}`)?.focus();
  };

  return (
    <section className="sec wrap" id="build">
      <SectionArt id="build" />
      <div className="sec-h rise">
        <SectionDivider label={DIVIDER.build} />
        <h2>One language, three editors.</h2>
        <p>Blocks, code and the copilot edit the same strategy.</p>
      </div>
      <div className="tabs" role="tablist" aria-label="Strategy level" onKeyDown={onKey}>
        {EDITOR_LEVELS.map((l, i) => (
          <button
            key={l.id}
            id={`lvl-${l.id}`}
            type="button"
            role="tab"
            aria-selected={i === level}
            aria-controls="lvl-panel"
            tabIndex={i === level ? 0 : -1}
            onClick={() => setLevel(i)}
          >
            {l.tab}
          </button>
        ))}
      </div>
      <div
        className="showcase rise"
        id="lvl-panel"
        role="tabpanel"
        aria-label={`${EDITOR_LEVELS[level].name} in the strategy editor`}
      >
        <ScreenFrame screen="editor" level={level} appHeight={600} />
      </div>
      <div className="cols rise">
        {COLUMNS.map(([h, p]) => (
          <div key={h}>
            <h3>{h}</h3>
            <p>{p}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
