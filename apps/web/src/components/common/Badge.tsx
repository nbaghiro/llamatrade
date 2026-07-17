import type { HTMLAttributes } from 'react';

export type BadgeVariant = 'primary' | 'accent' | 'gray' | 'success' | 'danger';

const VARIANT_CLASS: Record<BadgeVariant, string> = {
  primary: 'badge-primary',
  accent: 'badge-accent',
  gray: 'badge-gray',
  success: 'badge-success',
  danger: 'badge-danger',
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

/**
 * Badge — small uppercase tag. Composes `.badge` + a `.badge-*` variant.
 */
export function Badge({ variant = 'gray', className = '', ...rest }: BadgeProps) {
  const classes = ['badge', VARIANT_CLASS[variant], className].filter(Boolean).join(' ');
  return <span className={classes} {...rest} />;
}
