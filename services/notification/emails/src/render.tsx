/**
 * Build step: render the React templates to static HTML shells with
 * {{PLACEHOLDER}} slots, consumed at send time by the notification service
 * (src/email_render.py). One shell per (severity, cta) variant, so every
 * style decision stays here and Python only substitutes escaped content.
 *
 * Output is committed (like the generated protos): the Python service never
 * needs Node at runtime. Re-run `make emails` after editing a template.
 */

import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { render } from '@react-email/render';

import { TransactionalEmail } from './TransactionalEmail';
import type { Severity } from './theme';

const OUT_DIR = join(dirname(fileURLToPath(import.meta.url)), '../../src/email_html');

const SEVERITIES: Severity[] = ['info', 'actionable', 'critical', 'security'];

async function main(): Promise<void> {
  mkdirSync(OUT_DIR, { recursive: true });
  for (const severity of SEVERITIES) {
    for (const withCta of [false, true]) {
      const html = await render(
        <TransactionalEmail
          severity={severity}
          preheader="__PREHEADER__"
          title="__TITLE__"
          body="__BODY__"
          cta={withCta ? { url: '__CTA_URL__', label: '__CTA_LABEL__' } : undefined}
        />,
      );
      const name = `${severity}${withCta ? '_cta' : ''}.html`;
      writeFileSync(join(OUT_DIR, name), html);
      console.log(`rendered ${name} (${html.length} bytes)`);
    }
  }
}

await main();
