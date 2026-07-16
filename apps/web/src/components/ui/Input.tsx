import type { InputHTMLAttributes } from 'react';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Apply the `.input-error` red-ring state. Defaults to false. */
  error?: boolean;
}

/**
 * Input — bordered text field styled with the Monolith `.input` class.
 */
export function Input({ error = false, className = '', type = 'text', ...rest }: InputProps) {
  const classes = ['input', error ? 'input-error' : '', className].filter(Boolean).join(' ');
  return <input type={type} className={classes} {...rest} />;
}
