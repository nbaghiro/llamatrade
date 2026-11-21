import { LogoMark } from '../components/common/Logo';
import { APP_URL, MARKETING_STANDALONE, SIGN_IN_URL } from '../config/marketing';
import { useSignedIn } from '../marketing/hooks/useSignedIn';
import { footerLinks, type FooterLink } from '../marketing/lib/footer';

import { ModeToggle, WRAP } from './ui';

const LINK_OPTS = { standalone: MARKETING_STANDALONE, appUrl: APP_URL };

const PRODUCT: readonly FooterLink[] = [
  { label: 'How it works', href: '#how' },
  { label: 'Strategy language', href: '#build' },
  { label: 'Backtesting', href: '#backtest' },
  { label: 'Copilot', href: '#copilot' },
  { label: 'Paper and live sessions', href: '#live' },
  { label: 'FAQ', href: '#faq' },
];

function Column({ title, links }: { title: string; links: readonly FooterLink[] }) {
  if (links.length === 0) return null;
  return (
    <div className="grid content-start gap-2.5">
      <h5 className="m-0 mb-1 font-mono text-[11px] uppercase tracking-[0.12em] text-fg-3">
        {title}
      </h5>
      {links.map((l) => (
        <a key={l.label} href={l.href} className="text-[13.5px] text-fg-2 hover:text-fg">
          {l.label}
        </a>
      ))}
    </div>
  );
}

export function Footer() {
  const { access } = footerLinks(useSignedIn(), SIGN_IN_URL, LINK_OPTS);
  return (
    <footer className="border-t border-line">
      <div
        className={`${WRAP} grid grid-cols-1 gap-12 py-14 md:grid-cols-[minmax(0,1fr)_auto] md:gap-20`}
      >
        <div className="grid max-w-[460px] content-start gap-5">
          <a href="#top" aria-label="LlamaTrade, back to top" className="flex items-center gap-3">
            <LogoMark size={34} bold className="-my-2" />
            <span className="text-[12px] font-semibold uppercase tracking-[0.16em]">
              LlamaTrade
            </span>
          </a>
          <p className="m-0 text-[14px] text-fg-2">
            Algorithmic trading on your own Alpaca account. Sign-up is by invite.
          </p>
          <p className="m-0 text-[12px] leading-relaxed text-fg-3">
            Alpaca is the broker and holds the funds. Live sessions trade real money in your Alpaca
            account. Past results don&apos;t predict returns, and trading risks loss. Not investment
            advice. Figures are illustrative.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-10 sm:gap-16">
          <Column title="Product" links={PRODUCT} />
          <Column title="Access" links={access} />
        </div>
      </div>
      <div className={`${WRAP} flex items-center justify-between gap-4 border-t border-line py-5`}>
        <span className="font-mono text-[11.5px] text-fg-3">© 2026 LlamaTrade</span>
        <div className="flex items-center gap-4">
          <span className="hidden font-mono text-[11.5px] text-fg-3 sm:inline">
            Invite only · Paper and live trading
          </span>
          <ModeToggle />
        </div>
      </div>
    </footer>
  );
}
