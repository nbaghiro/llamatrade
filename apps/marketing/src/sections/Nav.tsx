import { Logo } from '@llamatrade/ui';

import { useAuthed } from '../hooks/useAuthed';

/**
 * Sticky top nav: brand mark (shared <Logo>) + in-page section links + a CTA
 * that adapts to the build. Local dev co-serves the web app through the reverse
 * proxy, so the CTA links into it — "Open App" → "/dashboard" for a signed-in
 * visitor (shared localStorage, see useAuthed), else "Join the beta" → "/login".
 * The standalone production build has no app, so the CTA is always the in-page
 * waitlist ("Join the beta" → "#join").
 */
export function Nav() {
  const authed = useAuthed();

  let cta = { href: '#join', label: 'Join the beta →' };
  if (import.meta.env.DEV) {
    cta = authed
      ? { href: '/dashboard', label: 'Open App →' }
      : { href: '/login', label: 'Join the beta →' };
  }

  return (
    <header className="nav">
      <div className="nav-inner">
        <a className="brand" href="#top" aria-label="LlamaTrade home">
          <Logo size={40} />
          <span>
            <span className="name">LlamaTrade</span>
            <span className="tag">Open · Algorithmic · Your account</span>
          </span>
        </a>
        <nav className="nav-links" aria-label="Primary">
          <a href="#build">01 Build</a>
          <a href="#backtest">02 Backtest</a>
          <a href="#copilot">03 Copilot</a>
          <a href="#live">04 Live</a>
          <a href="#own">05 Own it</a>
        </nav>
        <div className="nav-actions">
          <a className="nav-cta" href={cta.href}>
            {cta.label}
          </a>
        </div>
      </div>
    </header>
  );
}
