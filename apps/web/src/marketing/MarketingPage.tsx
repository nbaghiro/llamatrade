import { useEffect, useRef } from 'react';

import { Tape } from './components/Tape';
import { useReveal } from './hooks/useReveal';
import { Backtest } from './sections/Backtest';
import { Build } from './sections/Build';
import { Copilot } from './sections/Copilot';
import { Film } from './sections/Film';
import { Footer } from './sections/Footer';
import { Hero } from './sections/Hero';
import { Join } from './sections/Join';
import { Live } from './sections/Live';
import { Nav } from './sections/Nav';
import { Own } from './sections/Own';

import './marketing.css';

/**
 * The public site: one page, identical in Light and Dark. It renders at "/" and "/home" inside the
 * app and on its own from marketing.html. Every style is scoped under `.marketing-root`.
 */
export default function MarketingPage() {
  const root = useRef<HTMLDivElement>(null);
  useReveal(root);

  useEffect(() => {
    const html = document.documentElement;
    html.classList.add('marketing-active');
    return () => html.classList.remove('marketing-active');
  }, []);

  return (
    <div ref={root} className="site marketing-root">
      <Tape />
      <Nav />
      <main>
        <Hero />
        <Film />
        <Build />
        <Backtest />
        <Copilot />
        <Live />
        <Own />
        <Join />
      </main>
      <Footer />
    </div>
  );
}
