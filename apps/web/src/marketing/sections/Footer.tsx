import { LogoMark } from '../../components/common/Logo';
import { APP_URL, MARKETING_STANDALONE, SIGN_IN_URL } from '../../config/marketing';
import { SectionArt } from '../components/SectionArt';
import { ThemeSwitch } from '../components/ThemeSwitch';
import { useSignedIn } from '../hooks/useSignedIn';
import { footerLinks, PRODUCT_LINKS, type FooterLink } from '../lib/footer';

const LINK_OPTS = { standalone: MARKETING_STANDALONE, appUrl: APP_URL };

function Column({
  title,
  links,
  className,
}: {
  title: string;
  links: readonly FooterLink[];
  className: string;
}) {
  if (links.length === 0) return null;
  return (
    <div className={`fcol ${className}`}>
      <h5>{title}</h5>
      {links.map((l) => (
        <a key={l.label} href={l.href}>
          {l.label}
        </a>
      ))}
    </div>
  );
}

/** The closing lockup over the hero's candle chart, then the links, disclaimer and bottom row. */
export function Footer() {
  const { actions, access } = footerLinks(useSignedIn(), SIGN_IN_URL, LINK_OPTS);
  return (
    <footer className="fA fart-host">
      <SectionArt id="top" anchor=".close" />
      <div className="close wrap">
        <a className="lockup" href="#top" aria-label="LlamaTrade, back to top">
          <LogoMark className="logo-mark" size={128} bold />
          <span className="logo-word">LlamaTrade</span>
        </a>
        <p>Algorithmic trading on your own Alpaca account. Sign-up is by invite.</p>
        <div className="btns">
          {actions.map((a, i) => (
            <a key={a.label} className={i === 0 ? 'mk-btn pri' : 'mk-btn'} href={a.href}>
              {a.label}
              {i === 0 && (
                <i className="arr" aria-hidden="true">
                  →
                </i>
              )}
            </a>
          ))}
        </div>
      </div>
      <div className="wrap">
        <div className="fgrid rows">
          <div className="c1">
            <p className="fdisc">
              Alpaca is the broker and holds the funds. Live sessions trade real money in your
              Alpaca account. Past results don&apos;t predict returns, and trading risks loss. Not
              investment advice. Figures are illustrative.
            </p>
          </div>
          <div className="flinks">
            <Column title="Product" links={PRODUCT_LINKS} className="c2" />
            <Column title="Access" links={access} className="c3" />
          </div>
        </div>
        <div className="fgrid base">
          <span className="fmeta">© 2026 LlamaTrade</span>
          <div className="fend">
            <span className="fmeta">Invite only · Paper and live trading</span>
            <ThemeSwitch />
          </div>
        </div>
      </div>
    </footer>
  );
}
