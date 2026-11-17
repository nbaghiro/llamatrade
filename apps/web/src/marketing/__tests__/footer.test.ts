import { describe, expect, it } from 'vitest';

import { footerLinks } from '../lib/footer';

const IN_APP = { standalone: false };
const STANDALONE = { standalone: true, appUrl: 'https://app.example.com/' };
const STANDALONE_NO_APP = { standalone: true };

const labels = (links: readonly { label: string }[]) => links.map((l) => l.label);

describe('footerLinks', () => {
  it('offers the invite and sign-in to signed-out visitors', () => {
    const { actions, access } = footerLinks(false, '/login', IN_APP);
    expect(actions).toEqual([
      { label: 'Request an invite', href: '#join' },
      { label: 'Sign in', href: '/login' },
    ]);
    expect(access).toEqual([
      { label: 'Request an invite', href: '#join' },
      { label: 'Sign in', href: '/login' },
      { label: 'Connect Alpaca', href: '/login' },
    ]);
  });

  it('offers the app to signed-in visitors', () => {
    const { actions, access } = footerLinks(true, '/login', IN_APP);
    expect(actions).toEqual([{ label: 'Open app', href: '/dashboard' }]);
    expect(access).toEqual([
      { label: 'Open app', href: '/dashboard' },
      { label: 'Connect Alpaca', href: '/connect/alpaca' },
    ]);
  });

  it('links to the app origin from the standalone build', () => {
    const out = footerLinks(false, '/login', STANDALONE);
    expect(out.actions[1].href).toBe('https://app.example.com/login');
    expect(footerLinks(true, '/login', STANDALONE).actions[0].href).toBe(
      'https://app.example.com/dashboard'
    );
  });

  it('keeps only the invite when the standalone build has no app to link to', () => {
    for (const signedIn of [false, true]) {
      const { actions, access } = footerLinks(signedIn, '/login', STANDALONE_NO_APP);
      expect(labels(actions)).toEqual(['Request an invite']);
      expect(labels(access)).toEqual(['Request an invite']);
    }
  });
});
