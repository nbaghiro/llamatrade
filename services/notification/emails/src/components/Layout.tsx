import { Body, Container, Head, Html, Img, Preview, Section } from '@react-email/components';
import type { ReactNode } from 'react';

import { color, font } from '../theme';

/** The Monolith shell: bone canvas, one 600px paper card with a hard ink frame. */
export function Layout({ preheader, children }: { preheader: string; children: ReactNode }) {
  return (
    <Html lang="en">
      <Head />
      <Preview>{preheader}</Preview>
      <Body
        style={{
          margin: 0,
          padding: 0,
          backgroundColor: color.bone,
          backgroundImage: `repeating-linear-gradient(90deg, ${color.line} 0, ${color.line} 1px, transparent 1px, transparent 48px)`,
        }}
      >
        <Container style={{ maxWidth: '600px', margin: '0 auto', padding: '32px 16px 48px' }}>
          <Wordmark />
          <Section
            style={{
              backgroundColor: color.paper,
              border: `2px solid ${color.ink}`,
              boxShadow: `6px 6px 0 ${color.line}`,
            }}
          >
            {children}
          </Section>
          <Footer />
        </Container>
      </Body>
    </Html>
  );
}

function Wordmark() {
  return (
    <table role="presentation" cellPadding={0} cellSpacing={0} style={{ marginBottom: '14px' }}>
      <tbody>
        <tr>
          <td style={{ verticalAlign: 'middle', fontSize: 0, lineHeight: 0 }}>
            <Img
              src="__LOGO_URL__"
              width={34}
              height={34}
              alt="LlamaTrade"
              style={{ display: 'block' }}
            />
          </td>
          <td
            style={{
              paddingLeft: '12px',
              verticalAlign: 'middle',
              fontFamily: font.display,
              fontSize: '20px',
              letterSpacing: '0.08em',
              color: color.ink,
              textTransform: 'uppercase',
            }}
          >
            LlamaTrade
          </td>
        </tr>
      </tbody>
    </table>
  );
}

function Footer() {
  return (
    <Section style={{ paddingTop: '18px' }}>
      <p
        style={{
          margin: 0,
          fontFamily: font.mono,
          fontSize: '11px',
          lineHeight: '1.7',
          color: color.inkMuted,
        }}
      >
        You are receiving this because it concerns your LlamaTrade account.
        <br />
        Delivery preferences live in Settings → Notifications. Critical and security notices
        cannot be muted.
        <br />
        LlamaTrade · algorithmic trading, on your own brokerage account
      </p>
    </Section>
  );
}
