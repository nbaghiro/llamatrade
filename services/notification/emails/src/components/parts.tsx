import { Button, Section, Text } from '@react-email/components';

import { color, font, severityColor, severityLabel, type Severity } from '../theme';

export function SeverityTag({ severity }: { severity: Severity }) {
  const tint = severityColor[severity];
  return (
    <table role="presentation" cellPadding={0} cellSpacing={0}>
      <tbody>
        <tr>
          <td
            style={{
              border: `2px solid ${tint}`,
              padding: '3px 10px',
              fontFamily: font.mono,
              fontSize: '10px',
              fontWeight: 700,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              color: tint,
            }}
          >
            {severityLabel[severity]}
          </td>
        </tr>
      </tbody>
    </table>
  );
}

export function Title({ children }: { children: string }) {
  return (
    <Text
      style={{
        margin: '14px 0 0',
        fontFamily: font.display,
        fontSize: '26px',
        lineHeight: '1.15',
        letterSpacing: '0.01em',
        textTransform: 'uppercase',
        color: color.ink,
      }}
    >
      {children}
    </Text>
  );
}

export function BodyText({ children }: { children: string }) {
  return (
    <Text
      style={{
        margin: '14px 0 0',
        fontFamily: font.sans,
        fontSize: '15px',
        lineHeight: '1.65',
        color: color.ink,
      }}
    >
      {children}
    </Text>
  );
}

export function Cta({ url, label }: { url: string; label: string }) {
  return (
    <Section style={{ paddingTop: '22px' }}>
      <Button
        href={url}
        style={{
          backgroundColor: color.ink,
          color: color.bone,
          fontFamily: font.mono,
          fontSize: '13px',
          fontWeight: 700,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          textDecoration: 'none',
          padding: '13px 26px',
          border: `2px solid ${color.ink}`,
        }}
      >
        {label}
      </Button>
      <Text
        style={{
          margin: '14px 0 0',
          fontFamily: font.mono,
          fontSize: '11px',
          lineHeight: '1.6',
          color: color.inkMuted,
          wordBreak: 'break-all',
        }}
      >
        Or open this link directly: {url}
      </Text>
    </Section>
  );
}

/** The accent keel along the card's base, tinted by severity. */
export function Keel({ severity }: { severity: Severity }) {
  return (
    <table role="presentation" width="100%" cellPadding={0} cellSpacing={0}>
      <tbody>
        <tr>
          <td
            style={{
              height: '6px',
              backgroundColor: severityColor[severity],
              fontSize: 0,
              lineHeight: 0,
            }}
          />
        </tr>
      </tbody>
    </table>
  );
}
