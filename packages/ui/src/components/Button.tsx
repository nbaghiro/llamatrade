import type { ButtonHTMLAttributes } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: 'btn-primary',
  secondary: 'btn-secondary',
  ghost: 'btn-ghost',
  danger: 'btn-danger',
};

const SIZE_CLASS: Record<ButtonSize, string> = {
  sm: 'btn-sm',
  md: '',
  lg: 'btn-lg',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

/**
 * Button — thin prop-driven wrapper over the Monolith `.btn*` component classes.
 * Composes `.btn` + variant + size; any extra `className` is appended.
 */
export function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  type = 'button',
  ...rest
}: ButtonProps) {
  const classes = ['btn', VARIANT_CLASS[variant], SIZE_CLASS[size], className]
    .filter(Boolean)
    .join(' ');
  return <button type={type} className={classes} {...rest} />;
}
