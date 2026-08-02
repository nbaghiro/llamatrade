/**
 * Monolith theme tokens for email, mirrored from apps/web/src/styles/monolith.css.
 * Email clients cannot load webfonts reliably, so each stack leads with the
 * brand face and degrades to universally-available equivalents.
 */

export const color = {
  bone: '#fbf8f1',
  paper: '#ffffff',
  ink: '#0d0d0d',
  inkMuted: 'rgba(13, 13, 13, 0.62)',
  line: 'rgba(13, 13, 13, 0.14)',
  orange: '#ff4d1c',
  orangeDark: '#b8300b',
  red: '#c81e1e',
  green: '#0c6a2d',
  blue: '#24408a',
} as const;

export const font = {
  display: "'Anton', 'Arial Narrow', 'Helvetica Neue', Arial, sans-serif",
  sans: "'Archivo', -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif",
  mono: "'Space Mono', 'Courier New', Courier, monospace",
} as const;

export type Severity = 'info' | 'actionable' | 'critical' | 'security';

export const severityColor: Record<Severity, string> = {
  info: color.ink,
  actionable: color.orange,
  critical: color.red,
  security: color.blue,
};

export const severityLabel: Record<Severity, string> = {
  info: 'Notice',
  actionable: 'Action needed',
  critical: 'Critical',
  security: 'Security',
};
