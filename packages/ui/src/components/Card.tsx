import type { HTMLAttributes } from 'react';

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Add the brutalist hard-offset drop shadow (`.card-shadow`). Defaults to false. */
  shadow?: boolean;
}

/**
 * Card — bordered `paper` surface. Pass `shadow` for the hard-offset variant.
 */
export function Card({ shadow = false, className = '', ...rest }: CardProps) {
  const classes = [shadow ? 'card-shadow' : 'card', className].filter(Boolean).join(' ');
  return <div className={classes} {...rest} />;
}
