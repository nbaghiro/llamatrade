import { useRef } from 'react';

import { useWidth } from '../../components/charts/useWidth';
import { HeroArt } from '../components/HeroArt';
import { InviteForm } from '../components/InviteForm';
import { PhoneFrame, ScreenFrame } from '../components/ScreenFrame';
import { INDICATORS } from '../data/illustrative';
import { SMALL_SCREEN, useMedia } from '../hooks/useMedia';
import { stackLayout } from '../lib/frame';

const FACTS: readonly [string, string][] = [
  [String(INDICATORS.length), 'indicators in the language'],
  ['3', 'ways to build a strategy'],
  ['~80', 'templates to start from'],
  ['$0', 'during the closed beta'],
];

function Stack() {
  const [ref, width] = useWidth<HTMLDivElement>(0);
  const small = useMedia(SMALL_SCREEN);
  const layout = stackLayout(width, small);
  return (
    <div ref={ref} className="stack" style={{ height: width ? layout.height : undefined }}>
      {!small && (
        <>
          <ScreenFrame screen="editor" className="k-back l" />
          <ScreenFrame screen="portfolio" className="k-back r" />
        </>
      )}
      <ScreenFrame screen="backtest" className="k-main" />
      <PhoneFrame phone="home" className="k-phone l" style={{ top: layout.phoneTop }} />
      <PhoneFrame phone="strategy" className="k-phone r" style={{ top: layout.phoneTop }} />
    </div>
  );
}

export function Hero() {
  const section = useRef<HTMLElement>(null);
  const facts = useRef<HTMLDivElement>(null);
  return (
    <section ref={section} className="hero" id="top">
      <HeroArt section={section} facts={facts} />
      <div className="wrap hero-copy">
        <span className="mk-kicker">Closed beta · invite only · paper and live trading</span>
        <h1>Algorithmic trading on your own account.</h1>
        <p className="lede">
          Build a strategy, backtest it, then run it on Alpaca, in paper or live.
        </p>
        <div className="ctas">
          <InviteForm id="hero-invite" />
          <a className="cta-sub" href="#film">
            See the app <i aria-hidden="true">→</i>
          </a>
        </div>
      </div>
      <div className="wrap">
        <Stack />
      </div>
      <div className="wrap">
        <div ref={facts} className="facts rise">
          {FACTS.map(([n, label]) => (
            <div key={label}>
              <b>{n}</b>
              <span>{label}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
