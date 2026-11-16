import type { CSSProperties } from 'react';

interface SkeletonProps {
  className?: string;
  style?: CSSProperties;
  /** Hold still, for a refresh after the first load. */
  still?: boolean;
}

/** A grey block where content will land. Size it with className. */
export function Skeleton({ className = 'h-2.5 w-full', style, still = false }: SkeletonProps) {
  return (
    <span
      aria-hidden="true"
      style={style}
      className={`block rounded bg-sunk ${still ? '' : 'motion-safe:animate-pulse'} ${className}`}
    />
  );
}

/** A label above a large figure, as in a KPI or equity panel. */
export function SkeletonFigure({ className = '' }: { className?: string }) {
  return (
    <div className={`grid gap-2 ${className}`} aria-hidden="true">
      <Skeleton className="h-2.5 w-24" />
      <Skeleton className="h-7 w-44" />
      <Skeleton className="h-2.5 w-32" />
    </div>
  );
}

/** Table rows with a wider first column. */
export function SkeletonRows({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="divide-y divide-line" aria-hidden="true">
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="flex items-center gap-6 px-4 py-3">
          {Array.from({ length: cols }, (_, c) => (
            <Skeleton key={c} className={`h-2.5 ${c === 0 ? 'w-40' : 'w-16 ml-auto'}`} />
          ))}
        </div>
      ))}
    </div>
  );
}

/** Empty gridlines in place of a line chart, with no line that could read as data. */
export function SkeletonChart({ height = 220 }: { height?: number }) {
  return (
    <div className="relative" style={{ height }} aria-hidden="true">
      <div className="absolute inset-0 grid grid-rows-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="border-t border-dashed border-line" />
        ))}
      </div>
    </div>
  );
}

/** Screen-reader text for a loading region. */
export function LoadingLabel({ children = 'Loading' }: { children?: string }) {
  return (
    <span className="sr-only" role="status">
      {children}
    </span>
  );
}
