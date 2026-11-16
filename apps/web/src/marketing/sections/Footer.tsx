import { LogoMark } from '../../components/common/Logo';
import { APP_URL, MARKETING_STANDALONE, SIGN_IN_URL } from '../../config/marketing';
import { ThemeSwitch } from '../components/ThemeSwitch';
import { useSignedIn } from '../hooks/useSignedIn';
import { appHref } from '../lib/session';

type Link = { label: string; href: string | null };

const PRODUCT: readonly Link[] = [
  { label: 'Block editor', href: '#build' },
  { label: 'Copilot', href: '#copilot' },
  { label: 'Backtesting', href: '#backtest' },
  { label: 'Paper and live sessions', href: '#live' },
];

/** Links without a target yet stay hidden; a column with none left is dropped. */
const LEARN: readonly Link[] = [
  { label: 'Documentation', href: null },
  { label: 'Strategy language', href: null },
];

const LINK_OPTS = { standalone: MARKETING_STANDALONE, appUrl: APP_URL };

function accessLinks(signedIn: boolean): readonly Link[] {
  if (signedIn)
    return [
      { label: 'Open app', href: appHref('/dashboard', LINK_OPTS) },
      { label: 'Connect Alpaca', href: appHref('/connect/alpaca', LINK_OPTS) },
      { label: 'Community', href: null },
    ];
  return [
    { label: 'Request an invite', href: '#join' },
    { label: 'Sign in', href: appHref(SIGN_IN_URL, LINK_OPTS) },
    { label: 'Connect Alpaca', href: appHref(SIGN_IN_URL, LINK_OPTS) },
    { label: 'Community', href: null },
  ];
}

export function Closing() {
  return (
    <div className="closing">
      Build · Backtest · Paper and live sessions · Double-entry ledger · Encrypted keys
    </div>
  );
}

export function Footer() {
  const signedIn = useSignedIn();
  const COLUMNS: readonly [string, readonly Link[]][] = [
    ['Product', PRODUCT],
    ['Learn', LEARN],
    ['Access', accessLinks(signedIn)],
  ];
  const columns = COLUMNS.map(
    ([title, links]) =>
      [title, links.filter((l): l is { label: string; href: string } => !!l.href)] as const
  ).filter(([, links]) => links.length > 0);
  return (
    <footer className="wrap">
      <div className="foot">
        <div>
          <span className="logo">
            <LogoMark className="logo-mark" />
            LlamaTrade
          </span>
          <p>Algorithmic trading on your own Alpaca account. Closed beta, invite only.</p>
        </div>
        {columns.map(([title, links]) => (
          <div key={title}>
            <h5>{title}</h5>
            {links.map((l) => (
              <a key={l.label} href={l.href}>
                {l.label}
              </a>
            ))}
          </div>
        ))}
      </div>
      <p className="disc">
        Alpaca is the broker and holds the funds. Live sessions trade real money in your Alpaca
        account. Past results don&apos;t predict returns, and trading risks loss. Not investment
        advice. Figures are illustrative.
      </p>
      <div className="legal">
        <span>© 2026 LlamaTrade</span>
        <ThemeSwitch />
        <span>Closed beta · Invite only</span>
      </div>
    </footer>
  );
}
