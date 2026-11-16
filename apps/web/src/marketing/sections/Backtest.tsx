import { useCallback, useRef, useState } from 'react';

import { ScreenFrame } from '../components/ScreenFrame';
import { SectionArt } from '../components/SectionArt';
import { SectionDivider } from '../components/SectionDivider';
import { DIVIDER } from '../data/sections';
import { useOnEnter } from '../hooks/useReveal';

const PINS: readonly [string, string][] = [
  ['0', '36%'],
  ['100%', '27%'],
  ['100%', '62%'],
  ['0', '86%'],
];

const NOTES: readonly [string, string][] = [
  ['Run log', 'Streams progress. Cancel any time.'],
  ['Against SPY', 'Every figure beside the benchmark.'],
  ['Drawdown', 'The worst stretch, on its own scale.'],
  ['Monthly returns', 'Each month, shaded by size.'],
];

export function Backtest() {
  const annot = useRef<HTMLDivElement>(null);
  const [replay, setReplay] = useState(false);
  useOnEnter(
    annot,
    useCallback(() => setReplay(true), [])
  );

  return (
    <section className="sec wrap" id="backtest">
      <SectionArt id="backtest" />
      <div className="sec-h rise">
        <SectionDivider label={DIVIDER.backtest} />
        <h2>Backtest on the live engine.</h2>
        <p>Same code as a running session, so the decisions match.</p>
      </div>
      <div className="rise">
        <div ref={annot} className={`annot ${replay ? 'replay' : ''}`}>
          <ScreenFrame screen="backtest" />
          {PINS.map(([left, top], i) => (
            <span key={i} className="pin" style={{ left, top }} aria-hidden="true">
              {i + 1}
            </span>
          ))}
        </div>
      </div>
      <div className="notes4 rise">
        {NOTES.map(([h, p], i) => (
          <div key={h}>
            <i aria-hidden="true">{i + 1}</i>
            <p>
              <b>{h}</b>
              {p}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
