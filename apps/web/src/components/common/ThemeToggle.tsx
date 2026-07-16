interface ThemeToggleProps {
  /** Render inline (for header) vs floating (fixed position) */
  variant?: 'inline' | 'floating';
  /** Position for floating variant */
  position?: 'bottom-left' | 'bottom-right';
}

/**
 * Dark mode is retired in the Monolith theme. This component is intentionally a
 * no-op that renders nothing, so any remaining importers keep compiling without
 * a theme toggle ever appearing in the UI.
 */
export function ThemeToggle(_props: ThemeToggleProps) {
  return null;
}
