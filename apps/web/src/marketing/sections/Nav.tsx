import { LogoMark } from '../../components/common/Logo';
import { APP_URL, MARKETING_STANDALONE, SIGN_IN_URL } from '../../config/marketing';
import { useSignedIn } from '../hooks/useSignedIn';
import { appHref } from '../lib/session';

const LINKS: readonly [string, string][] = [
  ['#build', 'Build'],
  ['#backtest', 'Backtest'],
  ['#copilot', 'Copilot'],
  ['#live', 'Sessions'],
  ['#own', 'Your account'],
];

const LINK_OPTS = { standalone: MARKETING_STANDALONE, appUrl: APP_URL };

/** Signed-in visitors get "Open app"; everyone else gets "Sign in" beside the invite button. */
export function Nav() {
  const signedIn = useSignedIn();
  const open = appHref('/dashboard', LINK_OPTS);
  const signIn = appHref(SIGN_IN_URL, LINK_OPTS);
  return (
    <header className="nav">
      <div className="wrap">
        <a className="logo" href="#top" aria-label="LlamaTrade, back to top">
          <LogoMark className="logo-mark" size={60} bold />
          <span className="logo-word">LlamaTrade</span>
        </a>
        <nav className="links" aria-label="Sections">
          {LINKS.map(([href, label]) => (
            <a key={href} href={href}>
              {label}
            </a>
          ))}
        </nav>
        <div className="end">
          {signedIn && open ? (
            <a className="mk-btn pri" href={open}>
              Open app
            </a>
          ) : (
            <>
              {signIn && (
                <a className="mk-btn ghost" href={signIn}>
                  Sign in
                </a>
              )}
              <a className="mk-btn pri" href="#join">
                Request an invite
              </a>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
