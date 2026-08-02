import { Section } from '@react-email/components';

import { Layout } from './components/Layout';
import { BodyText, Cta, Keel, SeverityTag, Title } from './components/parts';
import type { Severity } from './theme';

export interface TransactionalEmailProps {
  severity: Severity;
  preheader: string;
  title: string;
  body: string;
  cta?: { url: string; label: string };
}

/** The one transactional shell every LlamaTrade email flows through. */
export function TransactionalEmail({
  severity,
  preheader,
  title,
  body,
  cta,
}: TransactionalEmailProps) {
  return (
    <Layout preheader={preheader}>
      <Section style={{ padding: '26px 28px 30px' }}>
        <SeverityTag severity={severity} />
        <Title>{title}</Title>
        <BodyText>{body}</BodyText>
        {cta && <Cta url={cta.url} label={cta.label} />}
      </Section>
      <Keel severity={severity} />
    </Layout>
  );
}
