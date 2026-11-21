import { Footer } from './Footer';
import { Hero } from './Hero';
import { Nav } from './Nav';
import { Backtest, Build, Copilot, Faq, How, Join, Live, Own } from './sections';

/** A second marketing site option: the demo video in a card over the candle art, then plain sections. */
export default function SitePage() {
  return (
    <div className="sn min-h-screen bg-canvas text-fg antialiased">
      <Nav />
      <main>
        <Hero />
        <How />
        <Build />
        <Backtest />
        <Copilot />
        <Live />
        <Own />
        <Join />
        <Faq />
      </main>
      <Footer />
    </div>
  );
}
