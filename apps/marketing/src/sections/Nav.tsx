import { Logo } from '@llamatrade/ui';

import { useAuthed } from '../hooks/useAuthed';

/**
 * Sticky top nav: brand mark (shared <Logo>) + in-page section links + a CTA.
 *
 * The section links are plain hash anchors (native smooth-scroll). The CTA is a
 * same-origin link served (through the reverse proxy) by the web app, so it is a
 * plain full-page navigation — no router needed here. It is auth-aware: an
 * already-signed-in visitor gets "Open App" → "/dashboard" (the app landing);
 * everyone else gets the sign-up CTA → "/login". Auth is read from the shared
 * localStorage auth store (see useAuthed), mirroring Galleo's marketing-site CTA
 * switch ("Go to app" when authed).
 */
export function Nav() {
  const authed = useAuthed();

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
          {authed ? (
            <a className="nav-cta" href="/dashboard">
              Open App →
            </a>
          ) : (
            <a className="nav-cta" href="/login">
              Join the beta →
            </a>
          )}
        </div>
      </div>
    </header>
  );
}
