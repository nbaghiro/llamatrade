import { appHref } from './session';

export interface FooterLink {
  label: string;
  href: string;
}

export interface FooterLinks {
  /** The closing buttons: the first is the primary action. */
  actions: readonly FooterLink[];
  access: readonly FooterLink[];
}

type LinkOpts = Parameters<typeof appHref>[1];

/** Links whose app target is hidden in this build are dropped. */
const present = (links: readonly { label: string; href: string | null }[]): FooterLink[] =>
  links.filter((l): l is FooterLink => l.href !== null);

export const PRODUCT_LINKS: readonly FooterLink[] = [
  { label: 'Block editor', href: '#build' },
  { label: 'Copilot', href: '#copilot' },
  { label: 'Backtesting', href: '#backtest' },
  { label: 'Paper and live sessions', href: '#live' },
];

/** Signed-in visitors get "Open app"; everyone else gets the invite and sign-in. */
export function footerLinks(signedIn: boolean, signInUrl: string, opts: LinkOpts): FooterLinks {
  const open = appHref('/dashboard', opts);
  const connect = appHref(signedIn ? '/connect/alpaca' : signInUrl, opts);
  if (signedIn && open) {
    const openApp = { label: 'Open app', href: open };
    return {
      actions: [openApp],
      access: present([openApp, { label: 'Connect Alpaca', href: connect }]),
    };
  }
  const invite = { label: 'Request an invite', href: '#join' };
  const signIn = { label: 'Sign in', href: appHref(signInUrl, opts) };
  return {
    actions: present([invite, signIn]),
    access: present([invite, signIn, { label: 'Connect Alpaca', href: connect }]),
  };
}
