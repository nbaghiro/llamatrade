/**
 * @llamatrade/ui — the "Monolith" design system.
 *
 * Presentational React components (no app state, no data fetching) plus the
 * Tailwind preset (`@llamatrade/ui/tailwind-preset`) and shared CSS layer
 * (`@llamatrade/ui/styles.css`). See the package README for consumption setup.
 */

export { Logo } from './components/Logo';
export type { LogoProps } from './components/Logo';

export { Button } from './components/Button';
export type { ButtonProps, ButtonVariant, ButtonSize } from './components/Button';

export { Card } from './components/Card';
export type { CardProps } from './components/Card';

export { Badge } from './components/Badge';
export type { BadgeProps, BadgeVariant } from './components/Badge';

export { Input } from './components/Input';
export type { InputProps } from './components/Input';

export { Label } from './components/Label';
export type { LabelProps } from './components/Label';

export { StrategyTree, prepareTree } from './components/StrategyTree';
export type {
  StrategyTreeProps,
  TreeNode,
  RawNode,
  BlockKind,
} from './components/StrategyTree';

export { Marquee } from './components/Marquee';
export type { MarqueeProps } from './components/Marquee';
