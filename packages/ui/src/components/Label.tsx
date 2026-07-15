import type { LabelHTMLAttributes } from 'react';

export type LabelProps = LabelHTMLAttributes<HTMLLabelElement>;

/**
 * Label — uppercase mono form label styled with the Monolith `.label` class.
 */
export function Label({ className = '', ...rest }: LabelProps) {
  const classes = ['label', className].filter(Boolean).join(' ');
  return <label className={classes} {...rest} />;
}
