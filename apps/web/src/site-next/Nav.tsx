import { Check } from 'lucide-react';

import { LogoMark } from '../components/common/Logo';
import { APP_URL, MARKETING_STANDALONE, SIGN_IN_URL } from '../config/marketing';
import { useInviteDone } from '../marketing/hooks/useInviteDone';
import { useSignedIn } from '../marketing/hooks/useSignedIn';
import { appHref } from '../marketing/lib/session';

import { WRAP } from './ui';

const LINKS: readonly [string, string][] = [
  ['#how', 'How it works'],
  ['#build', 'Build'],
  ['#backtest', 'Backtest'],
  ['#live', 'Sessions'],
  ['#own', 'Your account'],
  ['#faq', 'FAQ'],
];

const LINK_OPTS = { standalone: MARKETING_STANDALONE, appUrl: APP_URL };

const PILL =
  'inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 text-[13px] font-medium';

export function Nav() {
  const signedIn = useSignedIn();
  const [onList] = useInviteDone();
  const open = appHref('/dashboard', LINK_OPTS);
  const signIn = appHref(SIGN_IN_URL, LINK_OPTS);
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas">
      <div className={`${WRAP} flex h-14 items-center gap-6`}>
        <a href="#top" aria-label="LlamaTrade, back to top" className="flex items-center gap-3">
          <LogoMark size={30} bold className="-my-2" />
          <span className="text-[11.5px] font-semibold uppercase tracking-[0.16em]">
            LlamaTrade
          </span>
        </a>
        <nav aria-label="Sections" className="hidden flex-1 items-center gap-0.5 lg:flex">
          {LINKS.map(([href, label]) => (
            <a
              key={href}
              href={href}
              className="rounded-full px-3 py-1.5 text-[13px] text-fg-3 transition-colors hover:text-fg"
            >
              {label}
            </a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2 lg:ml-0">
          {signedIn && open ? (
            <a className={`${PILL} bg-fg text-canvas`} href={open}>
              Open app
            </a>
          ) : (
            <>
              {signIn && (
                <a
                  className={`${PILL} hidden text-fg-2 hover:text-fg sm:inline-flex`}
                  href={signIn}
                >
                  Sign in
                </a>
              )}
              {onList ? (
                <span className={`${PILL} text-fg-2`} role="status">
                  <Check size={14} strokeWidth={2.25} aria-hidden="true" className="text-gain" />
                  On the list
                </span>
              ) : (
                <a className={`${PILL} bg-fg text-canvas hover:bg-fg/85`} href="#join">
                  Request an invite
                </a>
              )}
            </>
          )}
        </div>
      </div>
    </header>
  );
}
