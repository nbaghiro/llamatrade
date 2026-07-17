import { useEffect } from 'react';

import { CursorAccent } from './components/CursorAccent';
import { GridOverlay } from './components/GridOverlay';
import { BottomMarquee, FeatureMarquee, TopTicker } from './components/Marquees';
import { useScrollReveal } from './hooks/useScrollReveal';
import { Backtest } from './sections/Backtest';
import { Build } from './sections/Build';
import { Copilot } from './sections/Copilot';
import { Cta } from './sections/Cta';
import { Footer } from './sections/Footer';
import { Hero } from './sections/Hero';
import { Live } from './sections/Live';
import { Nav } from './sections/Nav';
import { OwnIt } from './sections/OwnIt';

import './marketing.css';

/**
 * The LlamaTrade marketing landing — a faithful React port of the "Monolith"
 * landing page, consuming the shared Monolith design system (Logo,
 * Marquee, StrategyTree) and the Monolith theme tokens.
 *
 * Folded into apps/web so a single origin serves both marketing and the product.
 * The whole page renders inside `.marketing-root`, under which all of the
 * marketing-only CSS (marketing.css) is scoped so it never leaks into the app
 * shell. The `marketing-active` class on <html> enables the document-level
 * horizontal-overflow clamp + smooth anchor scrolling only while this page is
 * mounted.
 */
export default function MarketingPage() {
  useScrollReveal();

  useEffect(() => {
    const root = document.documentElement;
    root.classList.add('marketing-active');
    return () => root.classList.remove('marketing-active');
  }, []);

  return (
    <div className="marketing-root">
      <CursorAccent />
      <GridOverlay />
      <TopTicker />
      <Nav />
      <Hero />
      <FeatureMarquee />
      <Build />
      <Backtest />
      <Copilot />
      <Live />
      <OwnIt />
      <Cta />
      <BottomMarquee />
      <Footer />
    </div>
  );
}
